from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml


Role = Literal["prompt_a", "prompt_b"]


@dataclass
class SessionRecord:
    session_id: str
    created_at: str
    prompt_a_authenticated: bool
    prompt_b_authenticated: bool
    completed_at: str | None


class MarkdownSessionStore:
    def __init__(self, base_path: Path, master_key: str) -> None:
        self.base_path = base_path
        self.sessions_path = base_path / "sessions"
        self.master_key = master_key.encode("utf-8")
        self.sessions_path.mkdir(parents=True, exist_ok=True)

    def create_session(self) -> tuple[SessionRecord, str]:
        session_id = uuid.uuid4().hex
        created_at = _utc_now()
        shared_secret = secrets.token_urlsafe(32)
        salt = secrets.token_hex(16)
        secret_hash = _hash_secret(shared_secret, salt, self.master_key)

        frontmatter = {
            "session_id": session_id,
            "created_at": created_at,
            "secret_salt": salt,
            "secret_hash": secret_hash,
            "prompt_a_authenticated": False,
            "prompt_b_authenticated": False,
            "completed_at": None,
        }
        body = "# Shared AI Session\n\nThis markdown file tracks authentication for two prompts.\n"
        self._write_markdown(self._session_file(session_id), frontmatter, body)

        return (
            SessionRecord(
                session_id=session_id,
                created_at=created_at,
                prompt_a_authenticated=False,
                prompt_b_authenticated=False,
                completed_at=None,
            ),
            shared_secret,
        )

    def authenticate_prompt(self, session_id: str, role: Role, prompt_text: str, shared_secret: str) -> SessionRecord:
        frontmatter, _ = self._read_markdown(self._session_file(session_id))

        salt = frontmatter["secret_salt"]
        expected_hash = frontmatter["secret_hash"]
        candidate_hash = _hash_secret(shared_secret, salt, self.master_key)
        if not hmac.compare_digest(candidate_hash, expected_hash):
            raise PermissionError("Invalid shared secret for this session")

        timestamp = _utc_now()
        prompt_frontmatter = {
            "session_id": session_id,
            "role": role,
            "authenticated_at": timestamp,
        }
        prompt_body = f"# {role}\n\n{prompt_text.strip()}\n"
        self._write_markdown(self._prompt_file(session_id, role), prompt_frontmatter, prompt_body)

        frontmatter[f"{role}_authenticated"] = True
        if frontmatter["prompt_a_authenticated"] and frontmatter["prompt_b_authenticated"]:
            frontmatter["completed_at"] = timestamp

        summary = self._summary_body(frontmatter)
        self._write_markdown(self._session_file(session_id), frontmatter, summary)

        return SessionRecord(
            session_id=frontmatter["session_id"],
            created_at=frontmatter["created_at"],
            prompt_a_authenticated=bool(frontmatter["prompt_a_authenticated"]),
            prompt_b_authenticated=bool(frontmatter["prompt_b_authenticated"]),
            completed_at=frontmatter.get("completed_at"),
        )

    def get_session(self, session_id: str) -> SessionRecord:
        frontmatter, _ = self._read_markdown(self._session_file(session_id))
        return SessionRecord(
            session_id=frontmatter["session_id"],
            created_at=frontmatter["created_at"],
            prompt_a_authenticated=bool(frontmatter["prompt_a_authenticated"]),
            prompt_b_authenticated=bool(frontmatter["prompt_b_authenticated"]),
            completed_at=frontmatter.get("completed_at"),
        )

    def save_handoff(
        self,
        session_id: str,
        *,
        goal: str,
        current_status: str,
        last_successful_step: str,
        current_blocker: str,
        next_exact_step: str,
        paste_ready_inputs: str,
    ) -> None:
        # Validate the session exists before writing handoff data.
        self._read_markdown(self._session_file(session_id))

        frontmatter = {
            "session_id": session_id,
            "updated_at": _utc_now(),
        }
        body = (
            "# Shared Handoff\n\n"
            "## Goal\n"
            f"{goal.strip()}\n\n"
            "## Current Status\n"
            f"{current_status.strip()}\n\n"
            "## Last Successful Step\n"
            f"{last_successful_step.strip()}\n\n"
            "## Current Blocker\n"
            f"{current_blocker.strip()}\n\n"
            "## Next Exact Step\n"
            f"{next_exact_step.strip()}\n\n"
            "## Paste-ready Inputs\n"
            f"{paste_ready_inputs.strip()}\n"
        )
        self._write_markdown(self._handoff_file(session_id), frontmatter, body)

    def get_handoff(self, session_id: str) -> tuple[dict, str]:
        # Validate the session exists before reading handoff data.
        self._read_markdown(self._session_file(session_id))
        return self._read_markdown(self._handoff_file(session_id))

    def _session_file(self, session_id: str) -> Path:
        return self.sessions_path / f"{session_id}.md"

    def _prompt_file(self, session_id: str, role: Role) -> Path:
        prompt_dir = self.sessions_path / session_id
        prompt_dir.mkdir(parents=True, exist_ok=True)
        return prompt_dir / f"{role}.md"

    def _handoff_file(self, session_id: str) -> Path:
        prompt_dir = self.sessions_path / session_id
        prompt_dir.mkdir(parents=True, exist_ok=True)
        return prompt_dir / "handoff.md"

    @staticmethod
    def _write_markdown(path: Path, frontmatter: dict, body: str) -> None:
        content = f"---\n{yaml.safe_dump(frontmatter, sort_keys=False)}---\n\n{body.strip()}\n"
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _read_markdown(path: Path) -> tuple[dict, str]:
        if not path.exists():
            raise FileNotFoundError("Session not found")

        content = path.read_text(encoding="utf-8")
        if not content.startswith("---\n"):
            raise ValueError("Invalid markdown frontmatter")

        _, remainder = content.split("---\n", 1)
        frontmatter_text, body = remainder.split("---\n", 1)
        frontmatter = yaml.safe_load(frontmatter_text) or {}
        return frontmatter, body.strip()

    @staticmethod
    def _summary_body(frontmatter: dict) -> str:
        status = "complete" if frontmatter.get("completed_at") else "pending"
        return (
            "# Shared AI Session\n\n"
            f"- status: **{status}**\n"
            f"- prompt_a_authenticated: **{frontmatter['prompt_a_authenticated']}**\n"
            f"- prompt_b_authenticated: **{frontmatter['prompt_b_authenticated']}**\n"
            f"- completed_at: **{frontmatter.get('completed_at')}**\n"
        )


def _hash_secret(secret: str, salt: str, master_key: bytes) -> str:
    payload = (salt + secret).encode("utf-8")
    digest = hashlib.pbkdf2_hmac("sha256", payload, master_key, 100_000)
    return digest.hex()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
