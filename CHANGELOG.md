# Changelog

All notable changes. Versions follow [semantic versioning](https://semver.org): the number is in `VERSION` (and
`launcher/Cargo.toml`), and a release is published by itself when a push to `main` changes `VERSION`
(`.github/workflows/release.yml`, which also creates the tag `v<VERSION>`).

## [0.2.0] - 2026-11-12

### Three systems, one file each
- **macOS (Apple Silicon)** joins Windows and Linux. Every release now has exactly three files, each one both the
  install and the update: `SecurityModeler-Setup.exe` (Windows), `SecurityModeler-linux-x64` and
  `SecurityModeler-macos-arm64`. The `.tar.gz` + `install.sh` for Linux and the bare `.exe` for Windows are gone.
- **Windows setup** (Inno Setup): asks where to install (default `%LOCALAPPDATA%\SecurityModeler`, where 0.1 kept its
  data, so your map is found), adds Start-menu and optional Desktop shortcuts and an uninstaller that asks whether to
  keep your map.
- **Linux and macOS** install themselves: started from Downloads, the program asks where to install, copies itself
  there and adds an app-menu entry (Linux) or a `Security Modeler.app` inside that folder (macOS).
- The local LLM runs on macOS too (Ollama's `ollama-darwin.tgz`, Metal).

### Updates from inside the app
- The launcher checks GitHub a minute after it starts and every 6 hours. A newer version shows under the app's name in
  the sidebar (**Update to …**) and in the tray menu; one click downloads it, checks it against GitHub's SHA-256 of the
  file, and installs it into the same folder (Windows: the setup, silently; Linux/macOS: the program is swapped).
  Your map and settings are never touched.
- `--check-update` and `--uninstall` on the command line.

### Everything in the install folder
- Wherever it's installed, the app keeps everything in that one folder: the program, your map, Python, the LLM and its
  models, logs, temporary files and downloaded updates. uv no longer registers its Python in the Windows registry or
  puts shims in `~/.local/bin`; pip, temporary files and the tray icon's files stay in the folder; Ollama's key stays
  in `llm/home`.

### Look
- A new icon in the style of Akulav's other apps (a white shield with a check on an emerald-to-sky disc), used by the
  program, the tray, the setup and the browser tab. A new README.

### Versioning
- Versions now come from `VERSION` (`python tools_dev/bump_version.py X.Y.Z`) instead of being worked out from commit
  messages, and `ci.yml` tests the backend, the frontend and the launcher on all three systems on every push.
- Installs of 0.1.x have no updater: install 0.2.0 once by hand (on Windows, run the setup; your data in
  `%LOCALAPPDATA%\SecurityModeler` is kept). Later versions update themselves.

## [0.1.1]

- Visual updates.

## [0.1.0]

- First release: the interactive map, blast radius, questions, local AI analysis, PDF report and breach checks.
