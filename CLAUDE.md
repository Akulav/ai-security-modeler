# CLAUDE.md

Notes for working on **Security Modeler** (repo `ai-security-modeler`), made by Akulav. It maps a user's accounts,
devices and data and answers "what breaks if X is lost or hacked". Everything runs locally, the LLM included.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full picture and [CONTRIBUTING.md](CONTRIBUTING.md) for setup.

## Layout

- `backend/` — FastAPI app (`app/main.py`), routers in `app/routers/` (graph, analysis, hibp, llm, launcher, update),
  logic in `app/services/` (`graph_engine.py`, `questions.py`, `llm.py`, `hibp.py`, `redact.py`, `report_pdf.py`,
  `runtime.py`, `web_search.py`). SQLAlchemy models in `app/models.py`, schema upgrades in `app/upgrades.py`.
- `frontend/` — React + TypeScript (Vite). `npm run build` writes `frontend/dist`.
- `launcher/` — Rust program that becomes `SecurityModeler.exe` / `SecurityModeler-linux-x64`. Its build embeds
  `backend/app` and `frontend/dist`, so **build the frontend first**.

## Run and verify

```powershell
setup.bat                                                                       # first time
cd backend; ..\.venv\Scripts\python.exe -m pytest -q                            # backend tests (run from backend/)
cd backend; .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
cd frontend; npm run dev                                                        # http://127.0.0.1:5173
cd frontend; npm run build; cd ..\launcher; cargo build --release
cd launcher; cargo clippy --locked --all-targets -- -D warnings; cargo test --locked
```

- pytest must run from `backend/` (the tests import `app`); from the repo root it fails with `No module named 'app'`.
- Set `LLM_AUTO_SETUP=false` in `.env` during development to skip the large model download.
- Test the packaged exe against a scratch folder: `$env:SECURITY_MODELER_HOME = "$env:TEMP\sm-test"`. Never point
  it at the user's real data folder.

## Conventions & gotchas

- Privacy is the product: no cloud LLMs, no telemetry. Anything sent off-machine (HIBP, web search) goes through
  `services/redact.py` and must stay opt-in.
- The launcher runs the backend in a Windows job object so Quit / crash / Task Manager end the backend, Ollama and
  its runners. Keep that when touching process start-up.
- `launcher/assets/make_icon.py` regenerates every icon (web favicon, README logo, Linux tray pixels).
- Version lives in `VERSION`; note user-facing changes in `CHANGELOG.md`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships. It is local only (`graphify-out/` is git-ignored).

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost). If graphify-out/ is missing, rebuild it the same way.
