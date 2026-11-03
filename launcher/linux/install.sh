#!/bin/sh
# Installs Security Modeler for the current user: the program, a menu entry and its icon.
# Nothing goes outside your home folder, so this doesn't need sudo.
# Made by Akulav. https://github.com/Akulav/ai-security-modeler
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
bin="${HOME}/.local/bin"
data="${XDG_DATA_HOME:-${HOME}/.local/share}"

mkdir -p "$bin" "$data/applications" "$data/icons/hicolor/256x256/apps"
install -m 755 "$here/SecurityModeler" "$bin/SecurityModeler"
install -m 644 "$here/security-modeler.png" "$data/icons/hicolor/256x256/apps/security-modeler.png"
sed "s|^Exec=.*|Exec=$bin/SecurityModeler|" "$here/security-modeler.desktop" > "$data/applications/security-modeler.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$data/applications" || true

echo "Installed. Open Security Modeler from your app menu, or run: $bin/SecurityModeler"
case ":$PATH:" in
  *":$bin:"*) ;;
  *) echo "Note: $bin isn't on your PATH, so use the full path above to run it from a terminal." ;;
esac
