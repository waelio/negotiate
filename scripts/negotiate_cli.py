from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _request(base_url: str, method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc


def cmd_health(base_url: str) -> int:
    payload = _request(base_url, "GET", "/health")
    print(json.dumps(payload, indent=2))
    return 0


def cmd_demo_cycle(base_url: str) -> int:
    kickoff = _request(
        base_url,
        "POST",
        "/sessions/kickoff",
        {
            "prompt_text": "Prompt A opens negotiation with proposal terms.",
            "goal": "Reach agreement on scope, budget, and timeline",
            "current_blocker": "Awaiting prompt_b response",
            "next_exact_step": "Call /sessions/{session_id}/prompts/prompt_b with response",
        },
    )

    session_id = kickoff["session_id"]
    shared_secret = kickoff["shared_secret"]

    prompt_b = _request(
        base_url,
        "POST",
        f"/sessions/{session_id}/prompts/prompt_b",
        {
            "shared_secret": shared_secret,
            "prompt_text": "Prompt B responds with a counter-offer.",
        },
    )

    status = _request(base_url, "GET", f"/sessions/{session_id}")
    handoff = _request(base_url, "GET", f"/sessions/{session_id}/handoff")

    print("== Kickoff ==")
    print(json.dumps(kickoff, indent=2))
    print("\n== Prompt B Authentication ==")
    print(json.dumps(prompt_b, indent=2))
    print("\n== Session Status ==")
    print(json.dumps(status, indent=2))
    print("\n== Handoff ==")
    print(json.dumps(handoff, indent=2))
    print(f"\nSession ID: {session_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI for Prompt Session Auth Service")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="Check service health")
    subparsers.add_parser("demo-cycle", help="Run one full negotiation cycle")

    args = parser.parse_args()

    try:
        if args.command == "health":
            return cmd_health(args.base_url)
        if args.command == "demo-cycle":
            return cmd_demo_cycle(args.base_url)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
