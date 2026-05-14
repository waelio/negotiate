from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def _build_client() -> tuple[TestClient, object]:
    import app.main as main_module
    from app.storage import MarkdownSessionStore

    temp_dir = tempfile.TemporaryDirectory()
    store = MarkdownSessionStore(base_path=Path(temp_dir.name), master_key="test-master-key")
    main_module.store = store

    client = TestClient(main_module.app)
    return client, temp_dir


def test_create_session_and_authenticate_both_prompts() -> None:
    client, temp_dir = _build_client()
    try:
        create_resp = client.post("/sessions")
        assert create_resp.status_code == 200
        created = create_resp.json()

        session_id = created["session_id"]
        shared_secret = created["shared_secret"]

        auth_a_resp = client.post(
            f"/sessions/{session_id}/prompts/prompt_a",
            json={"shared_secret": shared_secret, "prompt_text": "Prompt A content"},
        )
        assert auth_a_resp.status_code == 200
        auth_a = auth_a_resp.json()
        assert auth_a["prompt_a_authenticated"] is True
        assert auth_a["prompt_b_authenticated"] is False
        assert auth_a["completed_at"] is None

        auth_b_resp = client.post(
            f"/sessions/{session_id}/prompts/prompt_b",
            json={"shared_secret": shared_secret, "prompt_text": "Prompt B content"},
        )
        assert auth_b_resp.status_code == 200
        auth_b = auth_b_resp.json()
        assert auth_b["prompt_a_authenticated"] is True
        assert auth_b["prompt_b_authenticated"] is True
        assert auth_b["completed_at"] is not None

        status_resp = client.get(f"/sessions/{session_id}")
        assert status_resp.status_code == 200
        status = status_resp.json()
        assert status["prompt_a_authenticated"] is True
        assert status["prompt_b_authenticated"] is True
        assert status["completed_at"] is not None
    finally:
        temp_dir.cleanup()


def test_rejects_invalid_shared_secret() -> None:
    client, temp_dir = _build_client()
    try:
        create_resp = client.post("/sessions")
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session_id"]

        auth_resp = client.post(
            f"/sessions/{session_id}/prompts/prompt_a",
            json={"shared_secret": "wrong-secret-1234", "prompt_text": "Prompt A content"},
        )

        assert auth_resp.status_code == 401
        assert "Invalid shared secret" in auth_resp.json()["detail"]
    finally:
        temp_dir.cleanup()


def test_404_for_missing_session() -> None:
    client, temp_dir = _build_client()
    try:
        status_resp = client.get("/sessions/does-not-exist")
        assert status_resp.status_code == 404
    finally:
        temp_dir.cleanup()


def test_save_and_get_handoff() -> None:
    client, temp_dir = _build_client()
    try:
        create_resp = client.post("/sessions")
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session_id"]

        save_resp = client.post(
            f"/sessions/{session_id}/handoff",
            json={
                "goal": "Finish antigravity token-limited task",
                "current_status": "Session created and both prompts authenticated",
                "last_successful_step": "Saved prompt_b",
                "current_blocker": "Daily token cap reached",
                "next_exact_step": "Resume from VS Code using saved handoff",
                "paste_ready_inputs": "session_id=...\nshared_secret=...",
            },
        )
        assert save_resp.status_code == 200
        assert save_resp.json()["status"] == "saved"

        get_resp = client.get(f"/sessions/{session_id}/handoff")
        assert get_resp.status_code == 200
        payload = get_resp.json()
        assert payload["session_id"] == session_id
        assert payload["updated_at"]
        assert "Finish antigravity token-limited task" in payload["body"]
        assert "Daily token cap reached" in payload["body"]
    finally:
        temp_dir.cleanup()


def test_kickoff_starts_prompt_a_and_saves_handoff() -> None:
    client, temp_dir = _build_client()
    try:
        kickoff_resp = client.post(
            "/sessions/kickoff",
            json={
                "prompt_text": "Prompt A starts the negotiation with opening terms.",
                "goal": "Reach agreement on budget and timeline",
                "current_blocker": "Waiting for prompt_b counter-offer",
                "next_exact_step": "Call /sessions/{session_id}/prompts/prompt_b with counter-offer",
            },
        )
        assert kickoff_resp.status_code == 200

        kickoff = kickoff_resp.json()
        assert kickoff["session_id"]
        assert kickoff["shared_secret"]
        assert kickoff["prompt_a_authenticated"] is True
        assert kickoff["prompt_b_authenticated"] is False
        assert kickoff["completed_at"] is None
        assert kickoff["handoff_saved"] is True

        session_id = kickoff["session_id"]

        handoff_resp = client.get(f"/sessions/{session_id}/handoff")
        assert handoff_resp.status_code == 200
        handoff = handoff_resp.json()
        assert "Reach agreement on budget and timeline" in handoff["body"]
        assert "Waiting for prompt_b counter-offer" in handoff["body"]

        prompt_b_resp = client.post(
            f"/sessions/{session_id}/prompts/prompt_b",
            json={
                "shared_secret": kickoff["shared_secret"],
                "prompt_text": "Prompt B counter-offer with revised timeline.",
            },
        )
        assert prompt_b_resp.status_code == 200
        status = prompt_b_resp.json()
        assert status["prompt_a_authenticated"] is True
        assert status["prompt_b_authenticated"] is True
        assert status["completed_at"] is not None
    finally:
        temp_dir.cleanup()
