"""Status of the local LLM runtime, and choosing, downloading and removing models."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, get_db
from ..models import AppSetting
from ..services.runtime import RuntimeError_, manager, normalize_model, valid_model_name

router = APIRouter(prefix="/api/llm", tags=["llm"])
SELECTED_KEY = "selected_model"
IDLE_KEY = "idle_unload_seconds"


class ModelRequest(BaseModel):
    model: str


class IdleRequest(BaseModel):
    seconds: int = Field(ge=0, le=86400)


def selected_model() -> str:
    with SessionLocal() as session:
        row = session.get(AppSetting, SELECTED_KEY)
    return normalize_model(row.value if row else settings.ollama_model)


def stored_idle_seconds() -> int:
    """The idle limit chosen in the app, or the .env default until one is chosen."""
    with SessionLocal() as session:
        row = session.get(AppSetting, IDLE_KEY)
    try:
        return max(0, int(row.value)) if row else settings.llm_idle_unload_seconds
    except ValueError:
        return settings.llm_idle_unload_seconds


def _store_selected(db: Session, model: str) -> None:
    db.merge(AppSetting(key=SELECTED_KEY, value=model))
    db.commit()


def _checked_name(model: str) -> str:
    if not valid_model_name(model):
        raise HTTPException(422, "That isn't a valid model name. Example: hf.co/owner/repo-GGUF:Q4_K_M")
    return normalize_model(model)


@router.get("/status")
async def status() -> dict:
    return {
        **await manager.status(),
        "selected": selected_model(),
        "default": normalize_model(settings.ollama_model),
        "idle_unload_seconds": manager.idle_seconds,
    }


@router.post("/idle", status_code=204)
async def set_idle(request: IdleRequest, db: Session = Depends(get_db)):
    db.merge(AppSetting(key=IDLE_KEY, value=str(request.seconds)))
    db.commit()
    await manager.set_idle_seconds(request.seconds)
    return Response(status_code=204)


@router.post("/select", status_code=204)
async def select(request: ModelRequest, db: Session = Depends(get_db)):
    model = _checked_name(request.model)
    if model not in await manager.installed_names():
        raise HTTPException(422, "That model isn't downloaded yet")
    _store_selected(db, model)
    return Response(status_code=204)


@router.post("/pull", status_code=202)
async def pull(request: ModelRequest):
    """Downloads a model, and selects it once the download succeeds."""
    model = _checked_name(request.model)

    def select_downloaded() -> None:
        with SessionLocal() as session:
            _store_selected(session, model)

    try:
        manager.pull(model, select_downloaded)
    except RuntimeError_ as error:
        raise HTTPException(409, str(error)) from error
    return {"model": model}


@router.post("/load", status_code=202)
async def load() -> dict:  # Async, because starting a background task needs the event loop.
    model = selected_model()
    try:
        manager.load(model)
    except RuntimeError_ as error:
        raise HTTPException(409, str(error)) from error
    return {"model": model}


@router.post("/unload", status_code=204)
async def unload():
    try:
        await manager.unload()
    except RuntimeError_ as error:
        raise HTTPException(409, str(error)) from error
    return Response(status_code=204)


@router.post("/cancel", status_code=204)
async def cancel():
    manager.cancel()
    return Response(status_code=204)


@router.post("/retry", status_code=204)
async def retry():
    manager.start(selected_model)
    return Response(status_code=204)


@router.delete("/models", status_code=204)
async def delete_model(request: ModelRequest, db: Session = Depends(get_db)):
    model = _checked_name(request.model)
    try:
        await manager.delete_model(model)
    except RuntimeError_ as error:
        raise HTTPException(502, str(error)) from error
    if selected_model() == model:
        remaining = await manager.installed_names()
        _store_selected(db, sorted(remaining)[0] if remaining else normalize_model(settings.ollama_model))
    return Response(status_code=204)
