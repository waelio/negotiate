# ⚡ Negotiate — AI vs AI Negotiation Platform

A fully serverless platform where two AI agents negotiate autonomously in real time, running entirely on Cloudflare.

🌐 **Live UI:** https://b717f7fe.negotiate-ui.pages.dev
🔧 **API Worker:** https://negotiate-api.waelio.workers.dev

---

## How it works

1. Set a **topic/goal** and **personas** for each agent
2. **Agent A** opens with a proposal (Cloudflare Workers AI — Llama 3)
3. **Agent B** counters with its own position
4. Sessions are persisted in **Cloudflare KV** with a shared secret for authentication
5. Hit **Continue Round** in the UI to run more back-and-forth turns

---

## Repository Structure

```
negotiate/
├── worker/              ← Cloudflare Worker (TypeScript API + AI)
│   ├── src/index.ts        API endpoints + AI agent logic
│   └── wrangler.toml       KV + Workers AI bindings
├── ui/
│   └── index.html          Live negotiation arena (Cloudflare Pages)
└── negotiate/           ← Original Python/FastAPI service (local dev)
    ├── app/
    │   ├── main.py          FastAPI endpoints
    │   └── storage.py       Markdown-backed session store
    ├── scripts/             CLI tools
    └── tests/
```

---

## Cloudflare Worker API

Base URL: `https://negotiate-api.waelio.workers.dev`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/health` | Health check |
| `POST` | `/negotiate/auto` | Start a full AI vs AI negotiation |
| `POST` | `/negotiate/auto/:id/continue` | Continue for another round |
| `POST` | `/sessions` | Create a bare session |
| `POST` | `/sessions/kickoff` | Open session with prompt A |
| `POST` | `/sessions/:id/prompts/:role` | Authenticate a prompt |
| `GET`  | `/sessions/:id` | Get session status |
| `POST` | `/sessions/:id/handoff` | Save handoff context |
| `GET`  | `/sessions/:id/handoff` | Read handoff context |
| `GET`  | `/sessions` | List recent sessions |

### Start an autonomous negotiation

```bash
curl -X POST https://negotiate-api.waelio.workers.dev/negotiate/auto \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Salary negotiation: candidate wants $180k, company budget is $150k",
    "agent_a_persona": "You are a job candidate. Be firm but professional.",
    "agent_b_persona": "You are an HR manager with a tight budget. Counter professionally."
  }'
```

### Continue to the next round

```bash
curl -X POST https://negotiate-api.waelio.workers.dev/negotiate/auto/<session_id>/continue \
  -H "Content-Type: application/json" \
  -d '{ "shared_secret": "<secret>" }'
```

---

## Deploy Your Own

### Worker

```bash
cd worker
npm install
npx wrangler kv namespace create SESSIONS   # paste returned id into wrangler.toml
npx wrangler deploy
```

### UI

```bash
# from repo root
npx wrangler pages deploy ui --project-name negotiate-ui
```

---

## Local Python Service

The `negotiate/` subdirectory is the original Python/FastAPI implementation:

```bash
cd negotiate
make setup   # create venv + install deps
make dev     # start on :8000
make demo    # run a full negotiation cycle
make test    # run tests
```

See [`negotiate/README.md`](./negotiate/README.md) for full Python API docs.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | Cloudflare Workers (TypeScript) |
| AI | Cloudflare Workers AI — `@cf/meta/llama-3-8b-instruct` |
| Storage | Cloudflare KV |
| UI | Cloudflare Pages (HTML/JS) |
| Local dev | Python / FastAPI / Ollama |

---

## Author

**Waelio** — [waelio.com](https://waelio.com) · [@waelio](https://github.com/waelio)
