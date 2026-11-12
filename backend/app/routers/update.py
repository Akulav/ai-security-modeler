"""Updates from inside the app. The desktop launcher checks GitHub and installs (launcher/src/update.rs); this page
only reads what it found (update.json in the data folder) and asks it to check or install by leaving a file there.

The header X-Security-Modeler is required on the two requests that act: a plain form on another website can't send
it, and a script there can't either, as the browser asks first and the CORS rules say no.
"""
import json

from fastapi import APIRouter, Header, HTTPException

from ..config import DATA_ROOT, settings

router = APIRouter(prefix="/api/update", tags=["update"])
HOME = DATA_ROOT  # (where the launcher keeps update.json)


def _managed() -> bool:
    """Started by an installed launcher, which is what installs updates."""
    return bool(settings.launcher_token)


@router.get("")
def update_status() -> dict:
    state: dict = {}
    try:
        state = json.loads((HOME / "update.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    managed = _managed() and state.get("managed", True)
    return {
        "managed": managed,
        "current": state.get("current"),
        "latest": state.get("latest"),
        "newer": bool(state.get("newer")) and managed,
        "notes": state.get("notes", ""),
        "page": state.get("page", ""),
        "state": state.get("state", ""),
        "error": state.get("error", ""),
        "checked": state.get("checked"),
    }


def _ask(name: str, header: str) -> None:
    if header != "1":
        raise HTTPException(403, "Only the app itself can ask for this")
    if not _managed():
        raise HTTPException(409, "Updates are installed by the desktop app. Run from source, use git pull instead.")
    (HOME / name).write_bytes(b"")


@router.post("/check", status_code=202)
def check_now(x_security_modeler: str = Header(default="")) -> dict:
    _ask("update.request", x_security_modeler)
    return {"ok": True}


@router.post("/install", status_code=202)
def install_now(x_security_modeler: str = Header(default="")) -> dict:
    _ask("update.apply", x_security_modeler)
    return {"ok": True}
