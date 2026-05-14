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

## Quickstart (usable command line)

Use these commands from the project root:

1. Setup local environment and dependencies:

- `make setup`

2. Start dev server:

- `make dev`

3. In another terminal, confirm health:

- `make health`

4. Run one full end-to-end negotiation cycle:

- `make demo`

5. Run tests:

- `make test`

CLI script entrypoint:

- `scripts/negotiate_cli.py`

Supported CLI commands:

- `python3 scripts/negotiate_cli.py health`
- `python3 scripts/negotiate_cli.py demo-cycle`
- `python3 scripts/negotiate_cli.py kickoff --prompt-text "..." --goal "..."`
- `python3 scripts/negotiate_cli.py auth <session_id> prompt_b --shared-secret "..." --prompt-text "..."`
- `python3 scripts/negotiate_cli.py status <session_id>`
- `python3 scripts/negotiate_cli.py handoff-get <session_id>`
- `python3 scripts/negotiate_cli.py handoff-save <session_id> --goal "..." --current-status "..." --last-successful-step "..." --current-blocker "..." --next-exact-step "..." --paste-ready-inputs "..."`

Optional base URL override:

- `python3 scripts/negotiate_cli.py --base-url http://127.0.0.1:8000 health`

Example full cycle with the enhanced existing CLI:

1. Kickoff with prompt A:

- `python3 scripts/negotiate_cli.py kickoff --prompt-text "Prompt A opens with proposal" --goal "Reach agreement"`

2. Authenticate prompt B with returned values:

- `python3 scripts/negotiate_cli.py auth <session_id> prompt_b --shared-secret "<shared_secret>" --prompt-text "Prompt B counter-offer"`

3. Read completion status:

- `python3 scripts/negotiate_cli.py status <session_id>`

4. Read shared handoff markdown:

- `python3 scripts/negotiate_cli.py handoff-get <session_id>`

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
