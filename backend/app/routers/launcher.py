"""Calls from the desktop launcher. Only it knows the token, so a web page can't quit the app."""
import hmac

from fastapi import APIRouter, Header, HTTPException, Response

from ..config import settings
from ..services.runtime import manager

router = APIRouter(prefix="/api/launcher", tags=["launcher"])


@router.post("/quit", status_code=204)
def quit_app(x_launcher_token: str = Header(default="")):
    """Stops the LLM runtime, freeing its RAM and VRAM. The launcher then ends this process."""
    if not settings.launcher_token or not hmac.compare_digest(x_launcher_token, settings.launcher_token):
        raise HTTPException(403, "Only the launcher can quit the app")
    manager.shutdown()
    return Response(status_code=204)
