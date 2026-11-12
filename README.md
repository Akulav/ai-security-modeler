<div align="center">

<img src="launcher/assets/icon-128.png" alt="Security Modeler" width="128" height="128">

# Security Modeler

**Map your accounts, devices and data, and see what breaks when one is lost or hacked. Made by Akulav.**

Everything runs on your own machine, the AI included. One file per system that installs and updates itself.

[![Latest release](https://img.shields.io/github/v/release/Akulav/ai-security-modeler?style=for-the-badge&label=release&color=34d399)](https://github.com/Akulav/ai-security-modeler/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/Akulav/ai-security-modeler/total?style=for-the-badge&color=0284c7)](https://github.com/Akulav/ai-security-modeler/releases)
[![Build](https://img.shields.io/github/actions/workflow/status/Akulav/ai-security-modeler/ci.yml?branch=main&style=for-the-badge&label=build)](https://github.com/Akulav/ai-security-modeler/actions/workflows/ci.yml)

![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?style=flat-square&logo=windows&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-x64-FCC624?style=flat-square&logo=linux&logoColor=black)
![macOS](https://img.shields.io/badge/macOS-Apple%20Silicon-000000?style=flat-square&logo=apple&logoColor=white)
![Local AI](https://img.shields.io/badge/AI-local%20only-2ea44f?style=flat-square&logo=ollama&logoColor=white)
![License](https://img.shields.io/badge/license-source--available-5c6270?style=flat-square)

### [⬇ Download the latest release](https://github.com/Akulav/ai-security-modeler/releases/latest)

</div>

---

<p align="center">
  <img src="docs/assets/screenshots/map.png" alt="A personal security map in Security Modeler, arranged as stars around the busiest nodes" width="100%">
</p>

Most security advice is generic. Security Modeler works from **your** setup, and answers the questions that matter:

> 📱 If I lose my phone, which accounts am I locked out of?
> 🔐 If my password manager is hacked, does my 2FA still protect anything?
> 🧩 Which accounts have no 2FA, and which of those matter most?
> 🔁 Do my accounts depend on each other in a loop I couldn't recover from?

## ⬇️ Download

One file per system. The same file installs the app the first time and updates it later.

| Platform | File | Notes |
| :-- | :-- | :-- |
| 🪟 **Windows 10 / 11** (x64) | [`SecurityModeler-Setup.exe`](https://github.com/Akulav/ai-security-modeler/releases/latest/download/SecurityModeler-Setup.exe) | Asks where to install. No admin rights needed. |
| 🐧 **Linux** (x64) | [`SecurityModeler-linux-x64`](https://github.com/Akulav/ai-security-modeler/releases/latest/download/SecurityModeler-linux-x64) | glibc 2.35+, GTK 3 and an AppIndicator library for the tray |
| 🍎 **macOS** (Apple Silicon) | [`SecurityModeler-macos-arm64`](https://github.com/Akulav/ai-security-modeler/releases/latest/download/SecurityModeler-macos-arm64) | macOS 14+ (Ollama's minimum), the AI runs on Metal |

Every release lists each file's SHA-256, and installed copies check updates against GitHub's own digest of the file.

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

### 🗺️ Interactive map
- Drag in **34 kinds of nodes**, from phones and routers to bank accounts and backups.
- Connect them with **22 relationship types**; only connections that make sense are offered.
- The star layout keeps even a password manager with 50 accounts readable.

</td>
<td width="50%" valign="top">

### 💥 Blast radius
- Click any node to see what fails **if it's lost** and what's exposed **if it's hacked**.
- Both are calculated separately: a lost authenticator and a hacked one hurt you in different ways.
- **14 ready-made questions**, such as *Which don't use TOTP but could?*, answered instantly from your map.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🧠 Local AI analysis
- A local LLM explains the findings, researches your services on the web and answers your questions.
- Set up automatically (portable Ollama, its own port), never leaves your machine.
- Frees all its RAM and VRAM after a minute without use, or from the tray.

</td>
<td width="50%" valign="top">

### 🔄 Reports and updates
- A shareable **PDF report** with a protection score, charts and every finding (addresses left out).
- Optional **HaveIBeenPwned** breach checks: breached accounts glow red.
- **One-click updates** from inside the app or the tray, verified with SHA-256, into the same folder.

</td>
</tr>
</table>

<p align="center">
  <img src="docs/assets/screenshots/blast-radius.png" alt="The blast radius of a lost phone, with every affected account lit up" width="49%">
  <img src="docs/assets/screenshots/questions.png" alt="The questions panel, ranking the least protected accounts" width="49%">
</p>
<p align="center">
  <img src="docs/assets/screenshots/report-cover.png" alt="The PDF report's cover, with the protection score" width="32%">
  <img src="docs/assets/screenshots/report-summary.png" alt="The PDF report's summary page, with charts and top fixes" width="32%">
</p>
<p align="center"><sub>Screenshots use the built-in sample map. The breach shown is fictional.</sub></p>

## 🚀 Getting started

### Windows
1. Download **`SecurityModeler-Setup.exe`** and run it.
2. Pick the install folder (default `%LOCALAPPDATA%\SecurityModeler`; any folder you can write to, e.g. `D:\Apps\SecurityModeler`). It adds Start-menu and (optional) Desktop
   shortcuts and an entry in *Settings → Apps*.
3. The app opens in your browser. Click **Load sample graph** to explore.

It lives in the **system tray**: click the icon to open the app; right-click it to unload the model, check for updates,
open the data or logs folder, or **Quit**, which frees all the RAM and VRAM the AI used. Uninstall from
*Settings → Apps*; the uninstaller asks whether to keep your map.

### Linux
```bash
chmod +x SecurityModeler-linux-x64
./SecurityModeler-linux-x64
```
It asks where to install (default `~/.local/share/SecurityModeler`), copies itself there, adds an app-menu entry and
starts. Running a newer download later updates the installed copy. Uninstall with `<install folder>/SecurityModeler --uninstall`.
On GNOME the tray icon needs the *AppIndicator* extension. Without a desktop it runs in the terminal (`--headless`).

### macOS (Apple Silicon)
```bash
chmod +x SecurityModeler-macos-arm64
xattr -d com.apple.quarantine SecurityModeler-macos-arm64
./SecurityModeler-macos-arm64
```
It asks where to install (default `~/Applications/Security Modeler`) and creates `Security Modeler.app` in that folder
(Launchpad, Spotlight). Its icon sits in the menu bar.

> 💡 The programs aren't code-signed (that needs a paid certificate): Windows SmartScreen may ask once (*More info → Run
> anyway*), macOS too (*System Settings → Privacy & Security → Open Anyway*).

## ⚙️ First start and memory

The app sets up its AI in the background, with progress on the canvas and in the tray, and the rest of the app works
meanwhile. Interrupted downloads resume, and later starts reuse the files.

| Download | Size |
| :-- | :-- |
| Python and the app's packages | about 100 MB |
| Portable Ollama, the local AI runtime | about 1.5 to 2.5 GB |
| The default model | about 16.3 GB |

The model runs best with about 16 GB of video memory and 32 GB of RAM. On smaller machines pick a smaller model, or skip
the AI: calculated findings, question lists and the PDF all work without it.

> [!NOTE]
> The default model is "abliterated": its refusal behaviour has been removed. It may follow malicious instructions in
> web results more readily than a standard model, so check its advice before acting on it. You can choose another
> default under [Configuration](#%EF%B8%8F-configuration).

## 📁 Where your data lives

**In the install folder you chose, and nowhere else.** The program, your map, settings, Python, the LLM and its models,
logs, temporary files and downloaded updates all live there; uv, pip, Python and Ollama are pointed at it too, so nothing
goes to `%APPDATA%`, `~/.cache`, `~/.ollama`, `/tmp` or the registry. Outside it there is only what makes it an app:
the Start menu / *Settings → Apps* entries on Windows (plus the optional Desktop shortcut) and the app-menu entry on
Linux, all removed by the uninstall. Updates never touch your data. Set `SECURITY_MODELER_HOME` to use another folder.

| Path | Contents |
| :-- | :-- |
| `data/modeler.db` | your map (unencrypted: use disk encryption) |
| `.env` | settings, created on first start |
| `llm/` | the portable Ollama and its models (delete it to free space; it downloads again) |
| `app/`, `packages/`, `python/`, `tools/` | the unpacked app and its Python, replaced when they change |
| `logs/` | launcher, backend and setup logs |
| `cache/` | uv and pip caches, temporary files, a downloaded update |
| `.install` | marks the folder (Linux, macOS) |
| `update.json` | what the last update check found |

## 🔒 Privacy

| Data | Where it goes |
| :-- | :-- |
| Your map, including email and IP addresses | Your data folder only, **unencrypted**. Use disk encryption such as BitLocker, FileVault or LUKS. |
| Passwords | Nowhere. The app records only a password's *type*, never the password. |
| What the AI sees | Only the local runtime on your machine. Email addresses are cut to their domain, IP addresses are removed. |
| Web searches by the AI | DuckDuckGo. Searches containing your addresses are blocked, but they can name services you use. Untick **Let the model search the web** to prevent that. |
| Breach checks | An address goes to HaveIBeenPwned when you save it, only if you've added a key. |
| Downloads and updates | GitHub, Python's package index and Hugging Face. None of your data is sent. |

The app listens only on `127.0.0.1` and has no login, so don't expose it to your network. More in the [security policy](SECURITY.md).

## 🛠️ Configuration

Settings live in `.env` in the data folder. Restart the app after changing it.

| Setting | Default | Purpose |
| :-- | :-- | :-- |
| `HIBP_API_KEY` | empty | [HaveIBeenPwned key](https://haveibeenpwned.com/API/Key) (paid). Breach checks stay off without it. |
| `LLM_AUTO_SETUP` | `true` | Set to `false` to use an Ollama you already run. |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | That Ollama's address, when auto setup is off. |
| `OLLAMA_MODEL` | `hf.co/huihui-ai/Huihui-Qwen3.8-27B-abliterated-GGUF` | Model used until you pick another in the app. Needs tool support for web research. |
| `OLLAMA_TIMEOUT_SECONDS` | `1800` | How long to wait for one AI call. |
| `OLLAMA_NUM_CTX` | `16384` | Context size. Raise it for very large maps. |
| `LLM_IDLE_UNLOAD_SECONDS` | `60` | Seconds without use before the model leaves memory. `0` keeps it loaded. |

The launcher also reads `SECURITY_MODELER_HOME` for the data folder and `SECURITY_MODELER_PORT` for its preferred port (8000).

## 🖥️ Command line

| Flag | Meaning |
| :-- | :-- |
| `--version` | Print the version and exit |
| `--background` | Start without opening the browser, for example from a startup entry |
| `--headless` | Run in the terminal, without a tray icon (automatic when there's no desktop) |
| `--here` | Run where it is instead of installing itself (Linux/macOS) |
| `--check-update` | Ask GitHub for the latest release |
| `--quit` | Quit a running copy |
| `--uninstall` | Remove the installed app (Windows: starts the uninstaller) |

<details>
<summary><b>🛠️ For maintainers: releases, updates and building</b></summary>

### Publishing a release

Releases are fully automated by [`.github/workflows/release.yml`](.github/workflows/release.yml):

1. `python tools_dev/bump_version.py 0.3.0` sets `VERSION`, `launcher/Cargo.toml` and `Cargo.lock`, and opens a section in [`CHANGELOG.md`](CHANGELOG.md).
2. Fill in the changelog, commit and push to `main`.
3. If the tag `v0.3.0` doesn't exist yet, CI runs the tests, builds all three systems, tags the commit and publishes a
   GitHub release with exactly three files, `SecurityModeler-Setup.exe`, `SecurityModeler-linux-x64` and
   `SecurityModeler-macos-arm64`, with the changelog's notes. *Actions → Release → Run workflow* retries a failed run.

[`ci.yml`](.github/workflows/ci.yml) runs on every push and pull request: the backend tests, the frontend type check,
and clippy + tests for the launcher on Windows, Linux and macOS, plus the Windows setup compiling.

### How updates are applied

The launcher checks the latest GitHub release a minute after it starts and every 6 hours (or on *Check for updates* in
the app or the tray) and writes what it found to `update.json`, which the app shows under its name in the sidebar.
**Update to …** downloads this system's file, checks it against GitHub's SHA-256 digest, then:

- **Windows:** quits the app and runs `SecurityModeler-Setup.exe /SILENT /UPDATE /DIR=<install folder>`; the setup
  ([`launcher/installer/security-modeler.iss`](launcher/installer/security-modeler.iss)) replaces the program and starts it again.
- **Linux / macOS:** swaps the program in the install folder in place (the old one is kept as `.old` until the next
  start) and starts the new one.

Code: `launcher/src/update.rs` (checking, downloading, applying), `launcher/src/install.rs` (self-install on
Linux/macOS), `backend/app/routers/update.py` and `frontend/src/components/UpdateNotice.tsx` (the in-app button).

### Building from source

```bash
cd frontend && npm ci && npm run build && cd ..
cd launcher && cargo build --release
```

The program is `launcher/target/release/SecurityModeler(.exe)`, with the backend and frontend packed inside. A cargo
build never installs or updates itself. The Windows setup needs [Inno Setup 6](https://jrsoftware.org/isinfo.php):

```bash
iscc /DAppVersion=0.2.0 /DExe=%CD%\launcher\target\release\SecurityModeler.exe /Odist launcher\installer\security-modeler.iss
```

Linux build dependencies: `sudo apt install libgtk-3-dev libxdo-dev libayatana-appindicator3-dev`. The icons are drawn
from `launcher/assets/icon.svg` by `python tools_dev/make_icons.py`. Backend tests: `cd backend && python -m pytest`.
More in [CONTRIBUTING.md](CONTRIBUTING.md) and the [architecture notes](docs/ARCHITECTURE.md).

</details>

## 📚 Documentation

| | |
| :-- | :-- |
| 📖 [User guide](docs/USER_GUIDE.md) | Modelling your setup, and what every setting means |
| 🏗️ [Architecture](docs/ARCHITECTURE.md) | How it fits together, and the API |
| 🤝 [Contributing](CONTRIBUTING.md) | Building from source, tests and releases |
| 🛡️ [Security policy](SECURITY.md) | Threat model, and how to report a problem |
| 📝 [Changelog](CHANGELOG.md) | What changed in each version |

## 🙏 Credits

Built with Rust (the launcher), Python and FastAPI (the backend), React, React Flow and Vite (the map), SQLite and
[Ollama](https://ollama.com) (the local AI). Icons by [Lucide](https://lucide.dev) (ISC).

---

<div align="center">

**Made with ❤️ by [Akulav](https://github.com/Akulav)**

<sub>© 2026 Akulav. Source-available under the <a href="LICENSE">Akulav Source-Available License</a>: run it, read it, change it privately; don't redistribute or sell it. Dependencies and models keep their own licenses.</sub>

</div>
