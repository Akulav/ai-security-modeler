# Personal Security & Infrastructure Modeler

Map your devices, accounts, network and data as an interactive graph, then see exactly what breaks when one of them is lost or hacked. Everything runs on your own machine, including the AI.

**Windows only for now.** The desktop app and automatic LLM setup target Windows.

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

These steps are for the copyright holder and anyone given written permission.

1. Download `SecurityModeler.exe` from the [latest release](https://github.com/Akulav/ai-security-modeler/releases/latest).
2. Run it. Nothing else needs installing: on first start it downloads its own Python and packages, which takes a minute or two.
3. The app opens in your browser at http://127.0.0.1:8000. Click **Load sample graph** on the empty canvas to try it.

The app runs in the background with an icon in the system tray. Click the icon to open the app. Right-click it to unload the model, open the data or logs folder, or **Quit**. Quitting stops the local LLM, which frees all the RAM and VRAM it used.

`SecurityModeler.exe --background` starts it without opening the browser, for example from a startup shortcut. `SecurityModeler.exe --quit` quits a running copy.

To run from source instead, see [Contributing](CONTRIBUTING.md).

### First start downloads about 18 GB

The app sets up its LLM in the background, with progress shown on the canvas and in the tray menu, and you can use the app meanwhile. Interrupted downloads resume, and later starts reuse the files.

| Download | Size | Saved to |
|---|---|---|
| Python and the app's packages | about 100 MB | `python`, `packages` |
| Portable Ollama | about 1.7 GB | `llm\ollama` |
| Default model | about 16.3 GB | `llm\models` |

Everything is saved in the data folder, `%LOCALAPPDATA%\SecurityModeler`. To keep it elsewhere, for example on a bigger drive, set the `SECURITY_MODELER_HOME` environment variable to another folder before starting the app.

### Memory

The model leaves RAM and VRAM after a minute without use, and loads again when needed. Change this under **Free RAM and VRAM** in the analysis panel, from one minute to never.

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
| Your map, including full email and IP addresses | Stored **unencrypted** in `data\modeler.db` in the data folder. Use disk encryption such as BitLocker. |
| Passwords | Nowhere. The app has no field for them, only for the password *type*. |
| Data sent to the LLM | Only the local runtime. Email addresses are reduced to their domain, and IP addresses are removed. Node names and notes are sent, with any addresses in them masked. |
| Web search queries | DuckDuckGo. Queries are shown in the log, and those containing your addresses are blocked. **They can still name services you use**, so untick "Let the model search the web" to prevent that. |
| Email address on a breach check | HaveIBeenPwned, automatically when you save a new address while a key is set. |
| First-run downloads | Fetched from GitHub, Python's package index and Hugging Face. Your data isn't sent. |

The server listens only on `127.0.0.1` and has no login, so don't expose it to your network.

## Configuration

Settings are in `.env` in the data folder, which the app creates on first start. Restart the app after any change: right-click the tray icon, **Quit**, then start it again.

| Setting | Default | Purpose |
|---|---|---|
| `HIBP_API_KEY` | empty | [HaveIBeenPwned key](https://haveibeenpwned.com/API/Key) (paid). Breach checks stay off without it. |
| `LLM_AUTO_SETUP` | `true` | Set to `false` to use an Ollama you already run. |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | That Ollama's address. Only used when auto setup is off. |
| `OLLAMA_MODEL` | `hf.co/huihui-ai/Huihui-Qwen3.8-27B-abliterated-GGUF` | Model used until you pick another in the app. Needs tool support for web research. |
| `OLLAMA_TIMEOUT_SECONDS` | `1800` | How long to wait for one LLM call. |
| `OLLAMA_NUM_CTX` | `16384` | Context size. Raise it for very large maps. Higher values use more memory and run slower. |
| `LLM_IDLE_UNLOAD_SECONDS` | `60` | Seconds without use before the model leaves memory. `0` keeps it until you unload it. The choice in the analysis panel overrides this. |

The launcher itself reads two environment variables: `SECURITY_MODELER_HOME` for the data folder, and `SECURITY_MODELER_PORT` for the port it prefers (8000). If that port is taken, it uses a free one.

## Tech stack

| Layer | Choice |
|---|---|
| Desktop launcher | Rust, with a system tray icon |
| Frontend | React, TypeScript, Vite, React Flow |
| Backend | Python, FastAPI, SQLAlchemy, ReportLab |
| Database | SQLite |
| LLM | Portable Ollama, with DuckDuckGo search as a tool |
| Breach data | HaveIBeenPwned API v3 |

## Uninstalling

Quit the app from its tray icon, then delete `SecurityModeler.exe` and the data folder, `%LOCALAPPDATA%\SecurityModeler`. To keep the app but remove only the LLM and its models, delete the `llm` folder inside it. It downloads again on the next start unless you set `LLM_AUTO_SETUP=false`.

## License

View only. All rights reserved. You may read this code, but you may not run, copy, modify or distribute it without written permission. See [LICENSE](LICENSE) for the full terms. Dependencies and models keep their own licenses.
