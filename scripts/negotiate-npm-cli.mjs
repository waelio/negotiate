#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";

const DEFAULT_BASE_URL = "http://127.0.0.1:8000";

function printHelp() {
  console.log(`negotiate (npm wrapper CLI)

Usage:
  negotiate help
  negotiate serve [--host 127.0.0.1] [--port 8000]
  negotiate health [--base-url http://127.0.0.1:8000]
  negotiate demo [--base-url http://127.0.0.1:8000]
  negotiate py-cli [...args]

Notes:
  - 'serve' runs the Python FastAPI app using uvicorn.
  - 'health' and 'demo' call HTTP endpoints directly.
  - Requires Python and service dependencies for runtime.
`);
}

function resolvePythonCommand() {
  const candidates = ["python3", "python"];
  for (const cmd of candidates) {
    const result = spawnSync(cmd, ["--version"], { stdio: "ignore" });
    if (result.status === 0) {
      return cmd;
    }
  }
  return null;
}

function getArgValue(flag, args, fallback) {
  const index = args.indexOf(flag);
  if (index >= 0 && index + 1 < args.length) {
    return args[index + 1];
  }
  return fallback;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.detail || payload?.error || `${response.status}`;
    throw new Error(`HTTP ${response.status}: ${detail}`);
  }
  return payload;
}

async function demo(baseUrl) {
  const kickoff = await requestJson(`${baseUrl}/sessions/kickoff`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt_text: "Prompt A opens negotiation with proposal terms.",
      goal: "Reach agreement on scope, budget, and timeline",
      current_blocker: "Awaiting prompt_b response",
      next_exact_step:
        "Submit prompt_b via /sessions/{session_id}/prompts/prompt_b",
    }),
  });

  const sessionId = kickoff.session_id;
  const sharedSecret = kickoff.shared_secret;

  const promptB = await requestJson(
    `${baseUrl}/sessions/${sessionId}/prompts/prompt_b`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        shared_secret: sharedSecret,
        prompt_text: "Prompt B responds with a counter-offer.",
      }),
    },
  );

  const status = await requestJson(`${baseUrl}/sessions/${sessionId}`);
  const handoff = await requestJson(`${baseUrl}/sessions/${sessionId}/handoff`);

  console.log("== Kickoff ==");
  console.log(JSON.stringify(kickoff, null, 2));
  console.log("\n== Prompt B Authentication ==");
  console.log(JSON.stringify(promptB, null, 2));
  console.log("\n== Session Status ==");
  console.log(JSON.stringify(status, null, 2));
  console.log("\n== Handoff ==");
  console.log(JSON.stringify(handoff, null, 2));
}

async function main() {
  const args = process.argv.slice(2);
  const command = args[0] || "help";

  if (command === "help" || command === "--help" || command === "-h") {
    printHelp();
    return;
  }

  if (command === "serve") {
    const python = resolvePythonCommand();
    if (!python) {
      throw new Error("Python is required but was not found in PATH.");
    }

    const host = getArgValue("--host", args, "127.0.0.1");
    const port = getArgValue("--port", args, "8000");

    const child = spawn(
      python,
      ["-m", "uvicorn", "app.main:app", "--host", host, "--port", String(port)],
      { stdio: "inherit", env: process.env },
    );

    child.on("exit", (code) => {
      process.exit(code ?? 0);
    });

    return;
  }

  if (command === "health") {
    const baseUrl = getArgValue("--base-url", args, DEFAULT_BASE_URL);
    const payload = await requestJson(`${baseUrl}/health`);
    console.log(JSON.stringify(payload, null, 2));
    return;
  }

  if (command === "demo") {
    const baseUrl = getArgValue("--base-url", args, DEFAULT_BASE_URL);
    await demo(baseUrl);
    return;
  }

  if (command === "py-cli") {
    const python = resolvePythonCommand();
    if (!python) {
      throw new Error("Python is required but was not found in PATH.");
    }

    const child = spawn(
      python,
      ["scripts/negotiate_cli.py", ...args.slice(1)],
      {
        stdio: "inherit",
        env: process.env,
      },
    );

    child.on("exit", (code) => {
      process.exit(code ?? 0);
    });

    return;
  }

  throw new Error(`Unknown command: ${command}`);
}

main().catch((error) => {
  console.error(`Error: ${error.message}`);
  process.exit(1);
});
