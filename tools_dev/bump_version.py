"""Set the app's version everywhere it's written, in one go:

    python tools_dev/bump_version.py 1.2.0

VERSION (what the app shows), launcher/Cargo.toml and launcher/Cargo.lock (the tray program; its build refuses a
mismatch), and a new section at the top of CHANGELOG.md to fill in. Then commit and push to main: the Release
workflow sees VERSION change, builds the programs, tags v1.2.0 and publishes them."""
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(new):
    if not re.fullmatch(r"\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?", new):
        sys.exit(f"{new!r} isn't a version like 1.2.0")
    (ROOT / "VERSION").write_text(new + "\n", encoding="utf-8")
    cargo = ROOT / "launcher" / "Cargo.toml"
    text = cargo.read_text(encoding="utf-8")
    cargo.write_text(re.sub(r'(?m)^version = "[^"]*"', f'version = "{new}"', text, count=1), encoding="utf-8")
    lock = ROOT / "launcher" / "Cargo.lock"
    if lock.exists():
        text = lock.read_text(encoding="utf-8")
        lock.write_text(re.sub(r'(name = "security-modeler"\nversion = )"[^"]*"', rf'\1"{new}"', text), encoding="utf-8")
    log = ROOT / "CHANGELOG.md"
    text = log.read_text(encoding="utf-8") if log.exists() else "# Changelog\n"
    if f"## [{new}]" not in text:
        head, _, rest = text.partition("\n## ")
        entry = f"## [{new}] - {datetime.date.today().isoformat()}\n\n- \n"
        text = f"{head.rstrip()}\n\n{entry}" + (f"\n## {rest}" if rest else "")
        log.write_text(text, encoding="utf-8")
    print(f"Version {new}: VERSION, launcher/Cargo.toml, Cargo.lock, CHANGELOG.md. Next: fill in CHANGELOG.md, "
          f"commit and push to main - the release v{new} is built and published by itself")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
