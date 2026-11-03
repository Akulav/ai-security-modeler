# Architecture

The app is one local process: FastAPI serves the API and the built React frontend from `127.0.0.1:8000`, and starts a portable Ollama on a free port.

```text
Browser (React Flow canvas)
   │  REST and streamed NDJSON
   ▼
FastAPI ──► SQLite (data/modeler.db)
   ├──► Graph engine: deterministic findings, no AI
   ├──► Ollama (llm/, local only) ──► web search tool ──► DuckDuckGo
   ├──► HaveIBeenPwned (optional)
   └──► ReportLab: PDF report
```

## Design decisions

**Facts come from code, explanations from the model.** The graph engine calculates findings and question lists, and gives them to the LLM as correct. The app stays useful without an LLM, and lists are always complete.

**Loss and compromise are separate calculations.** Each relationship in `catalog.py` declares three things:

| Property | Meaning |
|---|---|
| `provider` | Which end the other relies on |
| `loss` | What happens to the dependent if the provider is lost: `required`, `alternative`, `backup`, `network` or `none` |
| `compromise` | Whether an attacker on the provider also gains the dependent |

`loss_radius` grows a failed set to a fixed point, so dependency cycles can't fail by themselves. `compromise_radius` is a graph traversal along `compromise` links.

**Type rules live in one catalog.** `catalog.py` defines each type's fields, OS options, defenses and allowed relationships. The frontend receives this from `/api/catalog`, so a new type usually needs only a catalog entry and an icon in `visuals.ts`.

**Apps nodes are containers.** The engine replaces an Apps node with its device, so apps depend directly on the device and containers never appear in results.

**Least data to the model.** `redact.py` masks addresses before anything reaches the LLM, because a model that can search the web could otherwise leak them. Search queries are also checked before sending.

## Code map

```text
backend/app/
  main.py              App setup, security middleware, serves the frontend
  config.py            Settings from .env
  database.py          SQLite engine and startup upgrades
  models.py            Tables: nodes, edges, app_settings, saved_answers, analysis_reports
  schemas.py           Request and response validation
  catalog.py           Node types, fields, relationships and failure rules
  upgrades.py          Brings older maps up to date, type rules, automatic links
  seed.py              Sample graph
  routers/
    graph.py           Nodes, edges, blast radius, import and export
    analysis.py        Analysis, questions, PDF download
    llm.py             Runtime status and model management
    hibp.py            Breach checks
  services/
    graph_engine.py    Blast radius, findings
    questions.py       Ready-made questions, protection score
    llm.py             Ollama chat, research loop, report parsing
    runtime.py         Installs and runs portable Ollama, downloads models
    report_pdf.py      PDF report
    web_search.py      DuckDuckGo search tool
    hibp.py            HaveIBeenPwned client
    redact.py          Masking and search-query guard
backend/tests/         pytest suite
frontend/src/
  App.tsx              State and canvas wiring
  api.ts               Backend client, including streams
  layout.ts            Star and left-to-right layouts
  visuals.ts           Node icons and colours
  components/          Nodes, edges, panels, pickers and forms
```

These folders are created at run time and never committed: `data/`, `llm/`, `frontend/dist/` and `backend/.venv/`.

## API

All routes are under `/api`. Interactive documentation is at http://127.0.0.1:8000/docs while the app runs.

| Method and path | Purpose |
|---|---|
| `GET /catalog` | Types, fields and relationships |
| `GET /graph` | All nodes and edges |
| `POST /nodes`, `PATCH /nodes/{id}`, `DELETE /nodes/{id}` | Manage nodes |
| `GET /nodes/{id}/blast-radius` | What's lost and exposed |
| `POST /edges`, `PATCH /edges/{id}`, `DELETE /edges/{id}` | Manage relationships |
| `GET /export`, `POST /import` | Back up and replace the map |
| `POST /seed` | Load the sample into an empty map |
| `POST /analysis/run` | Full analysis (streamed) |
| `GET /analysis/latest` | Latest saved analysis |
| `POST /analysis/finish-research` | End web research and write the result |
| `GET /analysis/questions` | Questions with lists and saved answers |
| `POST /analysis/ask` | Ask the AI (streamed) |
| `GET /analysis/report.pdf` | Download the PDF report |
| `GET /llm/status` | Runtime and model status |
| `POST /llm/select`, `POST /llm/pull`, `DELETE /llm/models` | Manage models |
| `POST /llm/cancel`, `POST /llm/retry` | Pause a download, or retry setup |
| `POST /llm/load`, `POST /llm/unload` | Keep the model in memory, or free it and stop the runtime |
| `GET /hibp/status`, `POST /hibp/check/{id}`, `POST /hibp/advice/{id}` | Breach checks |

Streamed routes return newline-delimited JSON events such as `status`, `search`, `answer` and `done`.

## Startup upgrades

`init_db` adds missing columns, after making a timestamped backup, and then applies upgrades that are safe to repeat:

- folding old OS nodes into their device's OS field
- blanking fields a node's type doesn't have
- merging password and TOTP link pairs

To add a column, add it to the model and to `NEW_NODE_COLUMNS` in `upgrades.py`.
