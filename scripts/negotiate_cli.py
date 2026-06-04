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


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2))


def cmd_health(base_url: str) -> int:
    payload = _request(base_url, "GET", "/health")
    _print_json(payload)
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


def cmd_kickoff(args: argparse.Namespace) -> int:
    body: dict = {
        "prompt_text": args.prompt_text,
        "goal": args.goal,
        "current_blocker": args.current_blocker,
        "next_exact_step": args.next_exact_step,
        "paste_ready_inputs": args.paste_ready_inputs,
    }
    if args.context:
        body["context"] = args.context
    payload = _request(args.base_url, "POST", "/sessions/kickoff", body)
    _print_json(payload)
    return 0


def cmd_update_context(args: argparse.Namespace) -> int:
    body: dict = {"context": args.context}
    if args.goal:
        body["goal"] = args.goal
    payload = _request(
        args.base_url,
        "PATCH",
        f"/sessions/{args.session_id}/context",
        body,
    )
    _print_json(payload)
    return 0


def cmd_auth(args: argparse.Namespace) -> int:
    payload = _request(
        args.base_url,
        "POST",
        f"/sessions/{args.session_id}/prompts/{args.role}",
        {
            "shared_secret": args.shared_secret,
            "prompt_text": args.prompt_text,
        },
    )
    _print_json(payload)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    payload = _request(args.base_url, "GET", f"/sessions/{args.session_id}")
    _print_json(payload)
    return 0


def cmd_handoff_get(args: argparse.Namespace) -> int:
    payload = _request(args.base_url, "GET", f"/sessions/{args.session_id}/handoff")
    _print_json(payload)
    return 0


def cmd_handoff_save(args: argparse.Namespace) -> int:
    payload = _request(
        args.base_url,
        "POST",
        f"/sessions/{args.session_id}/handoff",
        {
            "goal": args.goal,
            "current_status": args.current_status,
            "last_successful_step": args.last_successful_step,
            "current_blocker": args.current_blocker,
            "next_exact_step": args.next_exact_step,
            "paste_ready_inputs": args.paste_ready_inputs,
        },
    )
    _print_json(payload)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI for Prompt Session Auth Service")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="Check service health")
    subparsers.add_parser("demo-cycle", help="Run one full negotiation cycle")

    kickoff_parser = subparsers.add_parser("kickoff", help="Create session + authenticate prompt_a + save handoff")
    kickoff_parser.add_argument("--prompt-text", required=True, help="Opening prompt text for prompt_a")
    kickoff_parser.add_argument("--goal", required=True, help="Negotiation goal")
    kickoff_parser.add_argument("--current-blocker", default="none", help="Current blocker")
    kickoff_parser.add_argument(
        "--next-exact-step",
        default="Submit prompt_b via /sessions/{session_id}/prompts/prompt_b",
        help="Next exact step",
    )
    kickoff_parser.add_argument("--paste-ready-inputs", default="", help="Optional handoff quick-copy inputs")
    kickoff_parser.add_argument(
        "--context",
        default=None,
        help="Custom context/instruction for the AI agent (overrides default negotiator role)",
    )

    auth_parser = subparsers.add_parser("auth", help="Authenticate prompt_a or prompt_b")
    auth_parser.add_argument("session_id", help="Session ID")
    auth_parser.add_argument("role", choices=["prompt_a", "prompt_b"], help="Prompt role")
    auth_parser.add_argument("--shared-secret", required=True, help="Shared secret returned from session create/kickoff")
    auth_parser.add_argument("--prompt-text", required=True, help="Prompt text to authenticate")

    status_parser = subparsers.add_parser("status", help="Get session status")
    status_parser.add_argument("session_id", help="Session ID")

    handoff_get_parser = subparsers.add_parser("handoff-get", help="Read shared handoff markdown")
    handoff_get_parser.add_argument("session_id", help="Session ID")

    handoff_save_parser = subparsers.add_parser("handoff-save", help="Write shared handoff markdown")
    handoff_save_parser.add_argument("session_id", help="Session ID")
    handoff_save_parser.add_argument("--goal", required=True, help="Current goal")
    handoff_save_parser.add_argument("--current-status", required=True, help="Current status")
    handoff_save_parser.add_argument("--last-successful-step", required=True, help="Last successful step")
    handoff_save_parser.add_argument("--current-blocker", required=True, help="Current blocker")
    handoff_save_parser.add_argument("--next-exact-step", required=True, help="Next exact step")
    handoff_save_parser.add_argument("--paste-ready-inputs", required=True, help="Copy/paste-ready values")

    update_context_parser = subparsers.add_parser("update-context", help="Update the negotiation context/instruction for a session")
    update_context_parser.add_argument("session_id", help="Session ID")
    update_context_parser.add_argument("--context", required=True, help="New context or instruction for the negotiation")
    update_context_parser.add_argument("--goal", default=None, help="Optional updated goal")

    args = parser.parse_args()

    try:
        if args.command == "health":
            return cmd_health(args.base_url)
        if args.command == "demo-cycle":
            return cmd_demo_cycle(args.base_url)
        if args.command == "kickoff":
            return cmd_kickoff(args)
        if args.command == "auth":
            return cmd_auth(args)
        if args.command == "status":
            return cmd_status(args)
        if args.command == "handoff-get":
            return cmd_handoff_get(args)
        if args.command == "handoff-save":
            return cmd_handoff_save(args)
        if args.command == "update-context":
            return cmd_update_context(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
