# Personal Security & Infrastructure Modeler

Map your devices, accounts, network and data as an interactive graph, then see exactly what breaks when one of them is lost or hacked. Everything runs on your own machine, including the AI.

**Windows only for now.** Automatic LLM setup and the launch scripts target Windows.

**View only.** This code is published for reading. Running, copying or modifying it requires written permission. See [License](#license).

## Why use it

Most personal security advice is generic. This works from your own setup, and answers questions like:

- If I lose my phone, which accounts am I locked out of?
- If my password manager is hacked, does my 2FA still protect anything?
- Which accounts have no 2FA, and which of those matter most?
- Do any of my accounts depend on each other in a loop I couldn't recover from?

## Features

- **Interactive map:** drag nodes onto a canvas and connect them. There are 34 node types across hardware, network gear, locations, software, accounts and data, and 22 relationship types. Only relationships that make sense for the two nodes are offered.
- **Blast radius:** click any node to see what fails **if lost** and what's exposed **if hacked**. They're calculated separately, because they spread differently.
- **Calculated findings:** single points of failure, takeover paths, circular dependencies, 2FA that falls together with the password, backup gaps and weak settings.
- **Local AI analysis:** a local LLM explains the findings and can research the web. It's set up automatically on first start, and you can choose another model.
- **Ready-made questions:** 14 questions, such as "Which don't use TOTP but could?". Each list is calculated instantly, and you can ask the AI for advice on it or type your own question.
- **PDF report:** a summary, charts, all findings, every account's protection score and saved AI answers. Email and IP addresses are left out.
- **Breach checks:** optional HaveIBeenPwned lookups. Breached accounts glow red and come with next steps.
- **Star and left-to-right layouts:** the star layout suits a password manager with dozens of accounts.

## Quick start

These steps are for the copyright holder and anyone given written permission. You need [Python 3.11+](https://www.python.org/downloads/) and [Node.js 20+](https://nodejs.org/). Double-click `run.bat` in the project folder. The first time, it installs everything first (you can also run `setup.bat` on its own).

Closing the window stops the app and the local LLM runtime it started. The app opens at http://127.0.0.1:8000. Click **Load sample graph** on the empty canvas to try it.

### First start downloads about 18 GB

The app sets up its LLM in the background, with progress shown on the canvas, and you can use the app meanwhile. Interrupted downloads resume, and later starts reuse the files.

| Download | Size | Saved to |
|---|---|---|
| Portable Ollama | about 1.7 GB | `llm/ollama` |
| Default model | about 16.3 GB | `llm/models` |

The default model runs best with about 16 GB of video memory and 32 GB of RAM. On smaller machines, choose a smaller model in the analysis panel, or skip the AI: calculated findings, question lists and the PDF work without it.

The default is an "abliterated" model, meaning its refusal behaviour has been removed. It may follow malicious instructions in web results more readily than a standard model, so check its advice before acting on it. To use a different default, see [Configuration](#configuration).

## Documentation

- [User guide](docs/USER_GUIDE.md): modelling your setup, and what every setting means
- [Architecture](docs/ARCHITECTURE.md): how the code fits together, and the API
- [Contributing](CONTRIBUTING.md): development setup and tests
- [Security policy](SECURITY.md): threat model and reporting problems

## Privacy

| Data | Where it goes |
|---|---|
| Your map, including full email and IP addresses | Stored **unencrypted** in `data/modeler.db`. Use disk encryption such as BitLocker. |
| Passwords | Nowhere. The app has no field for them, only for the password *type*. |
| Data sent to the LLM | Only the local runtime. Email addresses are reduced to their domain, and IP addresses are removed. Node names and notes are sent, with any addresses in them masked. |
| Web search queries | DuckDuckGo. Queries are shown in the log, and those containing your addresses are blocked. **They can still name services you use**, so untick "Let the model search the web" to prevent that. |
| Email address on a breach check | HaveIBeenPwned, automatically when you save a new address while a key is set. |
| First-run downloads | Fetched from GitHub and Hugging Face. Your data isn't sent. |

The server listens only on `127.0.0.1` and has no login, so don't expose it to your network.

## Configuration

Copy `.env.example` to `.env` (`setup.bat` does this for you), then restart the app after any change.

| Setting | Default | Purpose |
|---|---|---|
| `HIBP_API_KEY` | empty | [HaveIBeenPwned key](https://haveibeenpwned.com/API/Key) (paid). Breach checks stay off without it. |
| `LLM_AUTO_SETUP` | `true` | Set to `false` to use an Ollama you already run. |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | That Ollama's address. Only used when auto setup is off. |
| `OLLAMA_MODEL` | `hf.co/huihui-ai/Huihui-Qwen3.8-27B-abliterated-GGUF` | Model used until you pick another in the app. Needs tool support for web research. |
| `OLLAMA_TIMEOUT_SECONDS` | `1800` | How long to wait for one LLM call. |
| `OLLAMA_NUM_CTX` | `16384` | Context size. Raise it for very large maps. Higher values use more memory and run slower. |

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React, TypeScript, Vite, React Flow |
| Backend | Python, FastAPI, SQLAlchemy, ReportLab |
| Database | SQLite |
| LLM | Portable Ollama, with DuckDuckGo search as a tool |
| Breach data | HaveIBeenPwned API v3 |

## Uninstalling

Delete the project folder. To keep the app but remove only the LLM and its models, delete the `llm` folder. It downloads again on the next start unless you set `LLM_AUTO_SETUP=false`.

## License

View only. All rights reserved. You may read this code, but you may not run, copy, modify or distribute it without written permission. See [LICENSE](LICENSE) for the full terms. Dependencies and models keep their own licenses.
