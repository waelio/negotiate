# negotiate

Python service for authenticating **two AI prompts** against a **shared session**, with all session and prompt records stored as markdown (`.md`) files.

## What it does

- Creates a shared session and returns:
  - `session_id`
  - `shared_secret`
- Authenticates `prompt_a` and `prompt_b` using the same `shared_secret`
- Persists everything in markdown files under `data/sessions/`

## Project structure

- `app/main.py` — FastAPI app and endpoints
- `app/storage.py` — markdown-backed session store and auth logic
- `.env` — contains `APP_MASTER_KEY`

## Setup

1. Create a virtual environment and install dependencies from `requirements.txt`
2. Set a strong value in `.env` for `APP_MASTER_KEY`
3. Start the API with Uvicorn

Example run target:

- app import path: `app.main:app`
- host: `0.0.0.0`
- port: `8000`

## API

### Health check

- `GET /health`

### Create shared session

- `POST /sessions`

Response:

- `session_id`
- `shared_secret`
- `created_at`

### Kickoff negotiation with prompt A (recommended first step)

- `POST /sessions/kickoff`

This endpoint does three things in one call:

1. Creates a new session
2. Authenticates `prompt_a` using an internally generated shared secret
3. Saves initial shared progress to `handoff.md`

Request body:

- `prompt_text` (opening message from prompt A)
- `goal`
- `current_blocker`
- `next_exact_step`
- `paste_ready_inputs` (optional; auto-generated if empty)

Response includes:

- `session_id`
- `shared_secret` (use this for prompt B)
- `prompt_a_authenticated` (true)
- `prompt_b_authenticated` (false initially)
- `handoff_saved` (true)

### Authenticate prompt A or B

- `POST /sessions/{session_id}/prompts/{role}`
- `role` must be `prompt_a` or `prompt_b`

Request body:

- `shared_secret` (the one returned by session creation)
- `prompt_text`

Once both prompts authenticate successfully, the session is marked complete.

### Get session status

- `GET /sessions/{session_id}`

Returns whether each prompt is authenticated and whether the session is complete.

### Save shared handoff (resume context)

- `POST /sessions/{session_id}/handoff`

Request body fields:

- `goal`
- `current_status`
- `last_successful_step`
- `current_blocker`
- `next_exact_step`
- `paste_ready_inputs`

This writes `data/sessions/{session_id}/handoff.md` so you can pause in one AI tool and resume in another.

### Read shared handoff

- `GET /sessions/{session_id}/handoff`

Returns `session_id`, `updated_at`, and markdown `body` for easy resume.

## Markdown output

Files are written to:

- `data/sessions/{session_id}.md` — session frontmatter + summary
- `data/sessions/{session_id}/prompt_a.md` — authenticated prompt A text
- `data/sessions/{session_id}/prompt_b.md` — authenticated prompt B text
