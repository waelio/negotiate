/**
 * Negotiate API — Cloudflare Worker
 * Ports the Python/FastAPI negotiate service to run on Cloudflare Workers with KV storage.
 * Integrates Cloudflare Workers AI (like local_agent.py but serverless) so two AI agents
 * can negotiate autonomously without any local server.
 *
 * Endpoints:
 *   GET  /health
 *   POST /sessions                              → create session
 *   POST /sessions/kickoff                      → prompt_a opens + saves handoff
 *   POST /sessions/:id/prompts/:role            → authenticate prompt_a or prompt_b
 *   GET  /sessions/:id                          → session status
 *   POST /sessions/:id/handoff                  → save handoff context
 *   GET  /sessions/:id/handoff                  → read handoff context
 *   GET  /sessions                              → list recent sessions (for UI)
 *   POST /negotiate/auto                        → fully autonomous AI vs AI negotiation
 *   POST /negotiate/auto/:id/continue           → let Agent B counter-respond
 */

export interface Env {
  SESSIONS: KVNamespace;
  AI: Ai;  // Cloudflare Workers AI — replaces local Ollama agent
  MASTER_KEY?: string;
  CORS_ORIGIN?: string;
}

// ── AI helper ─────────────────────────────────────────────────────────────────

async function askAgent(
  ai: Ai,
  systemPrompt: string,
  userMessage: string
): Promise<string> {
  const response = await ai.run("@cf/meta/llama-3-8b-instruct", {
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userMessage },
    ],
    max_tokens: 512,
  }) as { response?: string };
  return response?.response?.trim() ?? "I accept your terms.";
}

// ── Types ────────────────────────────────────────────────────────────────────

interface SessionRecord {
  session_id: string;
  created_at: string;
  secret_hash: string;
  secret_salt: string;
  prompt_a_authenticated: boolean;
  prompt_b_authenticated: boolean;
  completed_at: string | null;
  prompt_a_text?: string;
  prompt_b_text?: string;
  negotiation?: NegotiationState;
}

interface HandoffRecord {
  session_id: string;
  updated_at: string;
  goal: string;
  current_status: string;
  last_successful_step: string;
  current_blocker: string;
  next_exact_step: string;
  paste_ready_inputs: string;
}

interface NegotiationTerm {
  label: string;
  agent_a_position: string;
  agent_b_position: string;
  priority: string;
}

interface NegotiationTurn {
  round: number;
  agent_a: string;
  agent_b: string;
  created_at: string;
}

interface NegotiationState {
  goal: string;
  terms: NegotiationTerm[];
  agent_a_persona: string;
  agent_b_persona: string;
  opening: string;
  history: NegotiationTurn[];
  rounds: number;
}

interface AutoNegotiationBody {
  goal?: string;
  agent_a_persona?: string;
  agent_b_persona?: string;
  opening?: string;
  terms?: Partial<NegotiationTerm>[];
}

// ── Crypto helpers ────────────────────────────────────────────────────────────

async function hashSecret(secret: string, salt: string, masterKey: string): Promise<string> {
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    enc.encode(masterKey),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const payload = enc.encode(salt + secret);
  const sig = await crypto.subtle.sign("HMAC", keyMaterial, payload);
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function randomHex(bytes = 16): string {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  return Array.from(arr)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function secureCompare(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}

// ── KV helpers ────────────────────────────────────────────────────────────────

async function getSession(kv: KVNamespace, id: string): Promise<SessionRecord | null> {
  const raw = await kv.get(`session:${id}`);
  return raw ? JSON.parse(raw) : null;
}

async function putSession(kv: KVNamespace, session: SessionRecord): Promise<void> {
  await kv.put(`session:${session.session_id}`, JSON.stringify(session), {
    expirationTtl: 60 * 60 * 24 * 7, // 7 days
  });
  // Maintain an index list for listing sessions
  const indexRaw = await kv.get("index:sessions");
  const index: string[] = indexRaw ? JSON.parse(indexRaw) : [];
  if (!index.includes(session.session_id)) {
    index.unshift(session.session_id);
    // Keep last 100 sessions in index
    await kv.put("index:sessions", JSON.stringify(index.slice(0, 100)));
  }
}

async function getHandoff(kv: KVNamespace, id: string): Promise<HandoffRecord | null> {
  const raw = await kv.get(`handoff:${id}`);
  return raw ? JSON.parse(raw) : null;
}

async function putHandoff(kv: KVNamespace, handoff: HandoffRecord): Promise<void> {
  await kv.put(`handoff:${handoff.session_id}`, JSON.stringify(handoff), {
    expirationTtl: 60 * 60 * 24 * 7,
  });
}

// ── CORS / Response helpers ───────────────────────────────────────────────────

function corsHeaders(origin: string): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
  };
}

function json(data: unknown, status = 200, origin = "*"): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...corsHeaders(origin),
    },
  });
}

function err(message: string, status = 400, origin = "*"): Response {
  return json({ detail: message }, status, origin);
}

// ── Session status shape (matches Python API) ─────────────────────────────────

function sessionStatus(s: SessionRecord) {
  return {
    session_id: s.session_id,
    created_at: s.created_at,
    prompt_a_authenticated: s.prompt_a_authenticated,
    prompt_b_authenticated: s.prompt_b_authenticated,
    completed_at: s.completed_at ?? null,
    prompt_a_text: s.prompt_a_text ?? null,
    prompt_b_text: s.prompt_b_text ?? null,
    negotiation: s.negotiation ?? null,
  };
}

// ── Negotiation helpers ───────────────────────────────────────────────────────

function normalizeTerms(goal: string, terms?: Partial<NegotiationTerm>[]): NegotiationTerm[] {
  const cleaned = (terms ?? [])
    .map((term) => ({
      label: term.label?.trim() ?? "",
      agent_a_position: term.agent_a_position?.trim() ?? "",
      agent_b_position: term.agent_b_position?.trim() ?? "",
      priority: term.priority?.trim() ?? "",
    }))
    .filter((term) => term.label || term.agent_a_position || term.agent_b_position);

  if (cleaned.length > 0) {
    return cleaned.map((term, index) => ({
      label: term.label || `Term ${index + 1}`,
      agent_a_position: term.agent_a_position || "State a concrete preferred outcome and fallback.",
      agent_b_position: term.agent_b_position || "State a concrete preferred outcome and fallback.",
      priority: term.priority || "medium",
    }));
  }

  return [
    {
      label: "Core agreement",
      agent_a_position: goal,
      agent_b_position: goal,
      priority: "high",
    },
  ];
}

function buildTermBrief(goal: string, terms: NegotiationTerm[]): string {
  const termLines = terms
    .map(
      (term, index) =>
        `${index + 1}. ${term.label} (priority: ${term.priority})\n` +
        `   Agent A wants: ${term.agent_a_position}\n` +
        `   Agent B wants: ${term.agent_b_position}`
    )
    .join("\n");

  return `Goal: ${goal}\n\nNegotiable terms:\n${termLines}`;
}

function buildHistoryTranscript(history: NegotiationTurn[]): string {
  if (history.length === 0) {
    return "No previous rounds.";
  }

  return history
    .map(
      (turn) =>
        `Round ${turn.round}\nAgent A: ${turn.agent_a}\nAgent B: ${turn.agent_b}`
    )
    .join("\n\n");
}

function realisticNegotiatorPrompt(persona: string, side: "A" | "B"): string {
  const counterpart = side === "A" ? "Agent B" : "Agent A";
  return `${persona}

You are negotiating like a real person with incentives, tradeoffs, and limits.
- Make specific offers with numbers, dates, quantities, scope, or other concrete terms when possible.
- Do not simply agree unless the current terms satisfy your stated interests.
- If you concede, ask for something in return and explain the tradeoff in one sentence.
- If the other side's offer violates a hard constraint, reject that term and provide a realistic counter.
- You may accept, counter-offer, ask one clarifying question, or walk away.
- Keep the response concise, but include enough detail for ${counterpart} to evaluate the offer.`;
}

// ── Router ────────────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = env.CORS_ORIGIN ?? "*";
    const masterKey = env.MASTER_KEY ?? "dev-master-key-change-in-production";

    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    const url = new URL(request.url);
    const path = url.pathname.replace(/\/$/, "") || "/";
    const method = request.method;

    // GET /health
    if (method === "GET" && path === "/health") {
      return json({ status: "ok" });
    }

    // GET /sessions — list recent sessions
    if (method === "GET" && path === "/sessions") {
      const indexRaw = await env.SESSIONS.get("index:sessions");
      const index: string[] = indexRaw ? JSON.parse(indexRaw) : [];
      const sessions = await Promise.all(
        index.map((id) => getSession(env.SESSIONS, id))
      );
      const existingSessions = sessions.filter(
        (session): session is SessionRecord => session !== null
      );
      return json(existingSessions.map(sessionStatus));
    }

    // POST /sessions — create session
    if (method === "POST" && path === "/sessions") {
      const session_id = randomHex(16);
      const created_at = new Date().toISOString();
      const shared_secret = randomHex(32);
      const secret_salt = randomHex(16);
      const secret_hash = await hashSecret(shared_secret, secret_salt, masterKey);

      const session: SessionRecord = {
        session_id,
        created_at,
        secret_hash,
        secret_salt,
        prompt_a_authenticated: false,
        prompt_b_authenticated: false,
        completed_at: null,
      };
      await putSession(env.SESSIONS, session);

      return json({ session_id, shared_secret, created_at });
    }

    // POST /sessions/kickoff
    if (method === "POST" && path === "/sessions/kickoff") {
      let body: {
        prompt_text?: string;
        goal?: string;
        current_blocker?: string;
        next_exact_step?: string;
        paste_ready_inputs?: string;
      };
      try {
        body = await request.json();
      } catch {
        return err("Invalid JSON body");
      }

      const { prompt_text, goal } = body;
      if (!prompt_text || !goal) {
        return err("prompt_text and goal are required");
      }

      const session_id = randomHex(16);
      const created_at = new Date().toISOString();
      const shared_secret = randomHex(32);
      const secret_salt = randomHex(16);
      const secret_hash = await hashSecret(shared_secret, secret_salt, masterKey);

      const session: SessionRecord = {
        session_id,
        created_at,
        secret_hash,
        secret_salt,
        prompt_a_authenticated: true,
        prompt_b_authenticated: false,
        completed_at: null,
        prompt_a_text: prompt_text,
      };
      await putSession(env.SESSIONS, session);

      const paste_ready_inputs =
        body.paste_ready_inputs?.trim() ||
        `session_id=${session_id}\nshared_secret=${shared_secret}\nnext_role=prompt_b`;

      const handoff: HandoffRecord = {
        session_id,
        updated_at: new Date().toISOString(),
        goal,
        current_status: "Prompt A started negotiation and authenticated successfully.",
        last_successful_step: "Saved prompt_a and authenticated it with shared_secret.",
        current_blocker: body.current_blocker ?? "none",
        next_exact_step:
          body.next_exact_step ??
          `Submit prompt_b response using shared_secret at POST /sessions/${session_id}/prompts/prompt_b`,
        paste_ready_inputs,
      };
      await putHandoff(env.SESSIONS, handoff);

      return json({
        session_id,
        shared_secret,
        created_at,
        prompt_a_authenticated: true,
        prompt_b_authenticated: false,
        completed_at: null,
        handoff_saved: true,
      });
    }

    // POST /sessions/:id/prompts/:role
    const promptMatch = path.match(/^\/sessions\/([^/]+)\/prompts\/(prompt_a|prompt_b)$/);
    if (method === "POST" && promptMatch) {
      const [, session_id, role] = promptMatch;
      let body: { shared_secret?: string; prompt_text?: string };
      try {
        body = await request.json();
      } catch {
        return err("Invalid JSON body");
      }
      const { shared_secret, prompt_text } = body;
      if (!shared_secret || !prompt_text) {
        return err("shared_secret and prompt_text are required");
      }

      const session = await getSession(env.SESSIONS, session_id);
      if (!session) return err("Session not found", 404);

      const candidate = await hashSecret(shared_secret, session.secret_salt, masterKey);
      if (!secureCompare(candidate, session.secret_hash)) {
        return err("Invalid shared secret for this session", 401);
      }

      if (role === "prompt_a") {
        session.prompt_a_authenticated = true;
        session.prompt_a_text = prompt_text;
      } else {
        session.prompt_b_authenticated = true;
        session.prompt_b_text = prompt_text;
      }

      if (session.prompt_a_authenticated && session.prompt_b_authenticated) {
        session.completed_at = new Date().toISOString();
      }

      await putSession(env.SESSIONS, session);
      return json(sessionStatus(session));
    }

    // GET /sessions/:id
    const sessionMatch = path.match(/^\/sessions\/([^/]+)$/);
    if (method === "GET" && sessionMatch) {
      const session = await getSession(env.SESSIONS, sessionMatch[1]);
      if (!session) return err("Session not found", 404);
      return json(sessionStatus(session));
    }

    // POST /sessions/:id/handoff
    const handoffPostMatch = path.match(/^\/sessions\/([^/]+)\/handoff$/);
    if (method === "POST" && handoffPostMatch) {
      const session_id = handoffPostMatch[1];
      const session = await getSession(env.SESSIONS, session_id);
      if (!session) return err("Session not found", 404);

      let body: Partial<HandoffRecord>;
      try {
        body = await request.json();
      } catch {
        return err("Invalid JSON body");
      }

      const required = ["goal", "current_status", "last_successful_step", "current_blocker", "next_exact_step", "paste_ready_inputs"];
      for (const field of required) {
        if (!body[field as keyof HandoffRecord]) {
          return err(`${field} is required`);
        }
      }

      const handoff: HandoffRecord = {
        session_id,
        updated_at: new Date().toISOString(),
        goal: body.goal!,
        current_status: body.current_status!,
        last_successful_step: body.last_successful_step!,
        current_blocker: body.current_blocker!,
        next_exact_step: body.next_exact_step!,
        paste_ready_inputs: body.paste_ready_inputs!,
      };
      await putHandoff(env.SESSIONS, handoff);
      return json({ status: "saved" });
    }

    // GET /sessions/:id/handoff
    const handoffGetMatch = path.match(/^\/sessions\/([^/]+)\/handoff$/);
    if (method === "GET" && handoffGetMatch) {
      const session = await getSession(env.SESSIONS, handoffGetMatch[1]);
      if (!session) return err("Session not found", 404);
      const handoff = await getHandoff(env.SESSIONS, handoffGetMatch[1]);
      if (!handoff) return err("Handoff not found — no handoff saved yet for this session", 404);
      return json(handoff);
    }

    // POST /negotiate/auto — Agent A proposes, Agent B counters, fully automated
    if (method === "POST" && path === "/negotiate/auto") {
      let body: AutoNegotiationBody;
      try {
        body = await request.json();
      } catch {
        return err("Invalid JSON body");
      }
      const goal = body.goal?.trim() || "Reach a mutually beneficial agreement";
      const personaA = body.agent_a_persona?.trim() || "You are Agent A, a firm but fair negotiator. Make a clear opening proposal.";
      const personaB = body.agent_b_persona?.trim() || "You are Agent B, a tough negotiator. Read the proposal and counter-offer or accept. Be concise.";
      const opening = body.opening?.trim() || `Let's negotiate about: ${goal}. I'll start with my opening proposal.`;
      const terms = normalizeTerms(goal, body.terms);
      const termBrief = buildTermBrief(goal, terms);

      // Create session
      const session_id = randomHex(16);
      const created_at = new Date().toISOString();
      const shared_secret = randomHex(32);
      const secret_salt = randomHex(16);
      const secret_hash = await hashSecret(shared_secret, secret_salt, masterKey);

      // Agent A generates its opening
      const agentAText = await askAgent(
        env.AI,
        realisticNegotiatorPrompt(personaA, "A"),
        `${termBrief}

Opening instruction: ${opening}

Your turn as Agent A: make a concrete opening offer across the important terms.`
      );

      const session: SessionRecord = {
        session_id, created_at, secret_hash, secret_salt,
        prompt_a_authenticated: true,
        prompt_b_authenticated: false,
        completed_at: null,
        prompt_a_text: agentAText,
      };
      await putSession(env.SESSIONS, session);

      // Agent B responds
      const agentBText = await askAgent(
        env.AI,
        realisticNegotiatorPrompt(personaB, "B"),
        `${termBrief}

Agent A's opening proposal:
${agentAText}

Your turn as Agent B: accept only if the offer meets your interests; otherwise counter with concrete terms.`
      );

      session.prompt_b_authenticated = true;
      session.prompt_b_text = agentBText;
      session.completed_at = new Date().toISOString();
      session.negotiation = {
        goal,
        terms,
        agent_a_persona: personaA,
        agent_b_persona: personaB,
        opening,
        history: [
          {
            round: 1,
            agent_a: agentAText,
            agent_b: agentBText,
            created_at: session.completed_at,
          },
        ],
        rounds: 1,
      };
      await putSession(env.SESSIONS, session);

      const handoff: HandoffRecord = {
        session_id,
        updated_at: new Date().toISOString(),
        goal,
        current_status: "Both agents exchanged concrete opening positions using the editable deal terms.",
        last_successful_step: "Agent B responded to Agent A's proposal with a realistic accept/counter decision.",
        current_blocker: "none",
        next_exact_step: `Continue negotiation at POST /negotiate/auto/${session_id}/continue`,
        paste_ready_inputs: `session_id=${session_id}\nshared_secret=${shared_secret}`,
      };
      await putHandoff(env.SESSIONS, handoff);

      return json({
        session_id,
        shared_secret,
        agent_a: agentAText,
        agent_b: agentBText,
        completed_at: session.completed_at,
        rounds: 1,
        negotiation: session.negotiation,
      });
    }

    // POST /negotiate/auto/:id/continue — let the negotiation continue for more rounds
    const continueMatch = path.match(/^\/negotiate\/auto\/([^/]+)\/continue$/);
    if (method === "POST" && continueMatch) {
      const session_id = continueMatch[1];
      const session = await getSession(env.SESSIONS, session_id);
      if (!session) return err("Session not found", 404);

      let body: AutoNegotiationBody & { shared_secret?: string };
      try { body = await request.json(); } catch { return err("Invalid JSON body"); }

      if (body.shared_secret) {
        const candidate = await hashSecret(body.shared_secret, session.secret_salt, masterKey);
        if (!secureCompare(candidate, session.secret_hash)) {
          return err("Invalid shared secret for this session", 401);
        }
      }

      const priorState = session.negotiation;
      const goal = body.goal?.trim() || priorState?.goal || "Reach a mutually beneficial agreement";
      const personaA =
        body.agent_a_persona?.trim() ||
        priorState?.agent_a_persona ||
        "You are Agent A. Review Agent B's counter-offer and respond — accept, counter, or walk away. Be concise.";
      const personaB =
        body.agent_b_persona?.trim() ||
        priorState?.agent_b_persona ||
        "You are Agent B. Review Agent A's response and counter or accept. Be concise.";
      const opening = body.opening?.trim() || priorState?.opening || `Continue negotiating about: ${goal}.`;
      const terms = normalizeTerms(goal, body.terms ?? priorState?.terms);
      const history =
        priorState?.history ??
        (session.prompt_a_text || session.prompt_b_text
          ? [
              {
                round: 1,
                agent_a: session.prompt_a_text ?? "",
                agent_b: session.prompt_b_text ?? "",
                created_at: session.completed_at ?? session.created_at,
              },
            ]
          : []);
      const nextRound = history.length + 1;
      const termBrief = buildTermBrief(goal, terms);
      const transcript = buildHistoryTranscript(history);

      // Agent A responds to B's last counter
      const newA = await askAgent(
        env.AI,
        realisticNegotiatorPrompt(personaA, "A"),
        `${termBrief}

Negotiation history:
${transcript}

Your turn as Agent A in round ${nextRound}: respond to Agent B's latest position. Accept only if your interests are met; otherwise counter with concrete concessions or a walk-away condition.`
      );

      // Agent B counters again
      const newB = await askAgent(
        env.AI,
        realisticNegotiatorPrompt(personaB, "B"),
        `${termBrief}

Negotiation history:
${transcript}

Agent A's round ${nextRound} response:
${newA}

Your turn as Agent B in round ${nextRound}: accept only if Agent A's terms meet your interests; otherwise counter with concrete concessions or a walk-away condition.`
      );

      const completedAt = new Date().toISOString();
      const nextHistory = [
        ...history,
        {
          round: nextRound,
          agent_a: newA,
          agent_b: newB,
          created_at: completedAt,
        },
      ];

      session.prompt_a_text = newA;
      session.prompt_b_text = newB;
      session.completed_at = completedAt;
      session.negotiation = {
        goal,
        terms,
        agent_a_persona: personaA,
        agent_b_persona: personaB,
        opening,
        history: nextHistory,
        rounds: nextRound,
      };
      await putSession(env.SESSIONS, session);

      return json({
        session_id,
        agent_a: newA,
        agent_b: newB,
        completed_at: session.completed_at,
        rounds: nextRound,
        negotiation: session.negotiation,
      });
    }

    return err("Not found", 404);
  },
};
