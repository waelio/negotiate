# AGENTS.md

## Cursor Cloud specific instructions

### Services

| Service | Description | How to run |
|---------|-------------|------------|
| Python FastAPI server | Core API for AI-vs-AI negotiation sessions | `make dev` (uvicorn on `127.0.0.1:8000` with `--reload`) |

The Cloudflare Worker (`worker/`) and static UI (`ui/`) are optional deployment targets and not needed for local development or testing.

### Key commands

See `Makefile` for the canonical list. Summary:

- **Setup**: `make setup` (creates `.venv`, installs deps)
- **Dev server**: `make dev` (starts uvicorn with hot reload on `:8000`)
- **Tests**: `make test` (runs pytest with `APP_MASTER_KEY=test-master-key`)
- **Health check**: `make health` (requires server running)
- **Demo cycle**: `make demo` (full end-to-end kickoff/auth/status/handoff; requires server running)

### Gotchas

- **`google-adk` dependency conflict**: `requirements.txt` includes `google-adk>=0.1.0` which requires `uvicorn>=0.34.0`, conflicting with the pinned `uvicorn==0.33.0`. Install the other packages individually (skipping `google-adk`). The app gracefully handles the missing import via try/except — only the `/sessions/kickoff-agent` endpoint is affected.
- **`.env` file required**: The server crashes on startup without `APP_MASTER_KEY` in `.env`. Tests pass their own key via environment variable and do not need the `.env` file.
- **No linter configured**: The repo has no linting tool configured (no ruff, flake8, eslint, etc.). Pytest is the only verification tool.
- **Session data is filesystem-based**: Sessions are stored as markdown files under `data/sessions/`. This directory is gitignored. No database setup required.
