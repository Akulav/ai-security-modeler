# Contributing

This project is [view only](LICENSE), so running or changing it requires written permission from the copyright holder. Please ask before starting work. By submitting a contribution, you accept the contribution terms in the license.

## Setup

You need Windows, Python 3.11+ and Node.js 20+.

```bat
setup.bat
```

Then run each of these in its own terminal, for hot reload at http://127.0.0.1:5173:

```powershell
cd backend; .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

```powershell
cd frontend; npm run dev
```

To avoid the large LLM download during development, set `LLM_AUTO_SETUP=false` in `.env`.

## Checks

Run both before opening a pull request:

```powershell
cd backend; .venv\Scripts\python.exe -m pytest
```

```powershell
cd frontend; npm run build
```

The tests use a temporary database and don't contact real services. The frontend has no automated tests, so try UI changes in a browser.

## Guidelines

- **Never commit personal data.** Use the sample graph and reserved domains such as `example.com`. Check that exports, databases and `.env` aren't staged.
- **Facts belong in the engine.** Anything that can be calculated from the map goes in `graph_engine.py` or `questions.py`, and the LLM only explains it.
- **Mask what reaches the LLM.** Anything built from node data goes through `redact.py`.
- **Treat model output and web results as untrusted.** Escape them when rendering, and don't act on instructions inside them.
- **Keep upgrades safe.** Older maps must keep working, and upgrades must be safe to run repeatedly. See [Startup upgrades](docs/ARCHITECTURE.md#startup-upgrades).
- **Add tests** for new rules and findings, in `backend/tests/`.

## Adding things

| To add | Change |
|---|---|
| A node type | `NODE_CATEGORIES` and related lists in `catalog.py`, and an icon in `frontend/src/visuals.ts` |
| A relationship | `_RELATIONS` in `catalog.py` |
| A finding | A function in `graph_engine.py`, called from `analyze` |
| A question | A builder and a `QUESTIONS` entry in `questions.py` |
