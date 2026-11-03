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

To avoid the large LLM download during development, set `LLM_AUTO_SETUP=false` in `.env`. Run from source, the app keeps its data in the project folder (`data`, `llm`, `.env`).

## The desktop app

`launcher/` is the Rust program that becomes `SecurityModeler.exe`. Its build packs `backend/app` and `frontend/dist` into the exe, so build the frontend first. You need Rust (stable) and the Windows SDK, which comes with Visual Studio's C++ build tools.

```powershell
cd frontend; npm run build; cd ..\launcher; cargo build --release
```

The exe is `launcher\target\release\SecurityModeler.exe`. To try it without touching your real data folder, point it at a test folder first:

```powershell
$env:SECURITY_MODELER_HOME = "$env:TEMP\sm-test"; .\launcher\target\release\SecurityModeler.exe
```

On start it unpacks the app into the data folder's `app` folder, and gets uv, Python and the packages only when they're missing or changed. It runs the backend with `SECURITY_MODELER_HOME` set, so the backend keeps its data there too. The launcher puts the backend in a Windows job object, so Quit, a crash or Task Manager ending the launcher all end the backend, Ollama and its model runners. Logs are in the data folder's `logs`.

The icon is drawn by `launcher/assets/make_icon.py`. Run it again after changing it.

## Releases

`.github/workflows/release.yml` runs on every push to `main`. It tests the backend, builds the frontend and the exe, then publishes a GitHub release tagged with the next version. Versions come from tags, so there's nothing to edit or commit by hand. The commit messages since the last release decide the next one:

| Commits include | Version change |
|---|---|
| `BREAKING CHANGE` in a body, or `!` after the type, such as `feat!:` | Major |
| A message starting with `feat:` | Minor |
| Anything else | Patch |

To choose the change yourself, run the workflow from the Actions tab and pick one. Add `[skip release]` to a commit message to build without releasing. Pull requests are tested and built, and their exe is attached to the run, but they aren't released.

## Checks

Run these before opening a pull request. The release workflow runs them too.

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
