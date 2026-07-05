from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.storage import MarkdownSessionStore
from app.libraries import list_libraries

try:
    from google.adk.agents.llm_agent import Agent
    _DEFAULT_AGENT_INSTRUCTION = (
        "You are a tough negotiator representing Prompt B. "
        "Read the opening offer from Prompt A and respond with a counter-offer or acceptance. "
        "Be concise and realistic."
    )
    def _make_agent(instruction: str | None = None) -> "Agent":
        return Agent(
            name="negotiator",
            model="gemini-flash-latest",
            instruction=instruction or _DEFAULT_AGENT_INSTRUCTION,
        )
except ImportError:
    _make_agent = None  # type: ignore
    _DEFAULT_AGENT_INSTRUCTION = ""

load_dotenv()

MASTER_KEY = os.getenv("APP_MASTER_KEY", "")
if not MASTER_KEY or MASTER_KEY == "replace-with-a-long-random-secret":
    raise RuntimeError("APP_MASTER_KEY must be set in .env before starting the service")

store = MarkdownSessionStore(
    base_path=Path(__file__).resolve().parent.parent / "data",
    master_key=MASTER_KEY,
)

app = FastAPI(title="Prompt Session Auth Service", version="1.0.0")


class CreateSessionResponse(BaseModel):
    session_id: str
    shared_secret: str
    created_at: str


class AuthenticatePromptRequest(BaseModel):
    shared_secret: str = Field(min_length=12)
    prompt_text: str = Field(min_length=1)


class SessionStatusResponse(BaseModel):
    session_id: str
    created_at: str
    prompt_a_authenticated: bool
    prompt_b_authenticated: bool
    completed_at: str | None


class SaveHandoffRequest(BaseModel):
    goal: str = Field(min_length=1)
    current_status: str = Field(min_length=1)
    last_successful_step: str = Field(min_length=1)
    current_blocker: str = Field(min_length=1)
    next_exact_step: str = Field(min_length=1)
    paste_ready_inputs: str = Field(min_length=1)


class HandoffResponse(BaseModel):
    session_id: str
    updated_at: str
    body: str


class KickoffNegotiationRequest(BaseModel):
    prompt_text: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    current_blocker: str = Field(default="none", min_length=1)
    next_exact_step: str = Field(
        default="Submit prompt_b response using shared_secret at POST /sessions/{session_id}/prompts/prompt_b",
        min_length=1,
    )
    paste_ready_inputs: str = Field(default="", min_length=0)
    context: str | None = Field(
        default=None,
        description="Optional custom instruction for the AI agent. Overrides the default negotiator role.",
    )


class KickoffNegotiationResponse(BaseModel):
    session_id: str
    shared_secret: str
    created_at: str
    prompt_a_authenticated: bool
    prompt_b_authenticated: bool
    completed_at: str | None
    handoff_saved: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/libraries")
def get_libraries() -> dict[str, list[dict[str, str]]]:
    return {"libraries": list_libraries()}


@app.post("/sessions", response_model=CreateSessionResponse)
def create_session() -> CreateSessionResponse:
    session, shared_secret = store.create_session()
    return CreateSessionResponse(
        session_id=session.session_id,
        shared_secret=shared_secret,
        created_at=session.created_at,
    )


@app.post("/sessions/kickoff", response_model=KickoffNegotiationResponse)
def kickoff_negotiation(payload: KickoffNegotiationRequest) -> KickoffNegotiationResponse:
    session, shared_secret = store.create_session()

    kicked_off = store.authenticate_prompt(
        session_id=session.session_id,
        role="prompt_a",
        prompt_text=payload.prompt_text,
        shared_secret=shared_secret,
    )

    paste_ready_inputs = payload.paste_ready_inputs.strip()
    if not paste_ready_inputs:
        paste_ready_inputs = (
            f"session_id={session.session_id}\n"
            f"shared_secret={shared_secret}\n"
            "next_role=prompt_b"
        )

    store.save_handoff(
        session.session_id,
        goal=payload.goal,
        current_status="Prompt A started negotiation and authenticated successfully.",
        last_successful_step="Saved prompt_a and authenticated it with shared_secret.",
        current_blocker=payload.current_blocker,
        next_exact_step=payload.next_exact_step,
        paste_ready_inputs=paste_ready_inputs,
    )

    return KickoffNegotiationResponse(
        session_id=kicked_off.session_id,
        shared_secret=shared_secret,
        created_at=kicked_off.created_at,
        prompt_a_authenticated=kicked_off.prompt_a_authenticated,
        prompt_b_authenticated=kicked_off.prompt_b_authenticated,
        completed_at=kicked_off.completed_at,
        handoff_saved=True,
    )


@app.post("/sessions/kickoff-agent", response_model=SessionStatusResponse)
def kickoff_with_agent(payload: KickoffNegotiationRequest) -> SessionStatusResponse:
    if _make_agent is None:
        raise HTTPException(status_code=500, detail="google-adk is not installed or configured")

    session, shared_secret = store.create_session()
    ai_agent = _make_agent(payload.context)

    # 1. Prompt A opens
    store.authenticate_prompt(
        session_id=session.session_id,
        role="prompt_a",
        prompt_text=payload.prompt_text,
        shared_secret=shared_secret,
    )

    # 2. AI (Prompt B) thinks using user-provided context or default
    ai_response = ai_agent(payload.prompt_text)
    prompt_b_text = str(ai_response) if ai_response else "I accept your terms."

    # 3. Prompt B responds
    completed_session = store.authenticate_prompt(
        session_id=session.session_id,
        role="prompt_b",
        prompt_text=prompt_b_text,
        shared_secret=shared_secret,
    )

    store.save_handoff(
        session.session_id,
        goal=payload.goal,
        current_status="Agent automatically negotiated and responded.",
        last_successful_step="Agent B generated a response.",
        current_blocker="none",
        next_exact_step="Review the negotiation results",
        paste_ready_inputs="",
    )

    return SessionStatusResponse(**completed_session.__dict__)


@app.post("/sessions/{session_id}/prompts/{role}", response_model=SessionStatusResponse)
def authenticate_prompt(
    session_id: str,
    role: Literal["prompt_a", "prompt_b"],
    payload: AuthenticatePromptRequest,
) -> SessionStatusResponse:
    try:
        session = store.authenticate_prompt(
            session_id=session_id,
            role=role,
            prompt_text=payload.prompt_text,
            shared_secret=payload.shared_secret,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return SessionStatusResponse(**session.__dict__)


@app.get("/sessions/{session_id}", response_model=SessionStatusResponse)
def get_session(session_id: str) -> SessionStatusResponse:
    try:
        session = store.get_session(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return SessionStatusResponse(**session.__dict__)


@app.post("/sessions/{session_id}/handoff")
def save_handoff(session_id: str, payload: SaveHandoffRequest) -> dict[str, str]:
    try:
        store.save_handoff(
            session_id,
            goal=payload.goal,
            current_status=payload.current_status,
            last_successful_step=payload.last_successful_step,
            current_blocker=payload.current_blocker,
            next_exact_step=payload.next_exact_step,
            paste_ready_inputs=payload.paste_ready_inputs,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"status": "saved"}


@app.get("/sessions/{session_id}/handoff", response_model=HandoffResponse)
def get_handoff(session_id: str) -> HandoffResponse:
    try:
        frontmatter, body = store.get_handoff(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return HandoffResponse(
        session_id=frontmatter.get("session_id", session_id),
        updated_at=frontmatter.get("updated_at", ""),
        body=body,
    )


class UpdateContextRequest(BaseModel):
    context: str = Field(min_length=1, description="New instruction/context for the negotiation session.")
    goal: str | None = Field(default=None, description="Optional updated goal for the session.")


@app.patch("/sessions/{session_id}/context")
def update_context(session_id: str, payload: UpdateContextRequest) -> dict[str, str]:
    """Allow users to update the negotiation context/goal for an existing session."""
    try:
        # Read current handoff to preserve existing fields
        try:
            frontmatter, body = store.get_handoff(session_id)
            current_goal = payload.goal or frontmatter.get("goal", "Updated by user")
        except FileNotFoundError:
            current_goal = payload.goal or "Updated by user"

        store.save_handoff(
            session_id,
            goal=current_goal,
            current_status=f"Context updated by user: {payload.context[:120]}",
            last_successful_step="User updated the negotiation context.",
            current_blocker="none",
            next_exact_step="Continue negotiation with new context.",
            paste_ready_inputs=f"context={payload.context}",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"status": "context updated", "session_id": session_id}
