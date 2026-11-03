"""Breach checks for nodes that hold an email address."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Node
from ..schemas import NodeOut
from ..services import hibp, llm
from ..services.graph_engine import blast_radius
from ..services.redact import mask_text
from .graph import edge_dicts, node_dicts
from .llm import selected_model

router = APIRouter(prefix="/api/hibp", tags=["hibp"])


@router.get("/status")
def status() -> dict:
    return {"configured": bool(settings.hibp_api_key)}


@router.post("/check/{node_id}", response_model=NodeOut)
async def check_node(node_id: str, db: Session = Depends(get_db)):
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(404, "Node not found")
    if not node.email:
        raise HTTPException(422, "This node has no email address")
    try:
        breaches = await hibp.check_email(node.email)
    except hibp.HibpError as error:
        raise HTTPException(error.status_code, error.message) from error

    node.breaches = breaches
    node.breach_checked_email = node.email
    node.breach_checked_at = datetime.now(timezone.utc)
    node.breach_advice = hibp.fallback_advice(node.name, breaches) if breaches else None
    db.commit()
    return node


@router.post("/advice/{node_id}", response_model=NodeOut)
async def advise_node(node_id: str, model: str | None = None, db: Session = Depends(get_db)):
    """Replaces the built-in advice with LLM advice. Keeps the built-in text if Ollama is down."""
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(404, "Node not found")
    if not node.breaches:
        raise HTTPException(422, "This node has no recorded breaches")

    names = {n["id"]: n["name"] for n in node_dicts(db)}
    radius = blast_radius(node_dicts(db), edge_dicts(db), node_id)
    dependents = [mask_text(names[i]) for i in {*radius["dependents"], *radius["compromise"]}]
    try:
        advice = await llm.breach_advice(
            mask_text(node.name), node.type, dependents, node.breaches, model or selected_model(),
        )
    except llm.LlmError as error:
        raise HTTPException(503, str(error)) from error
    if advice:
        node.breach_advice = advice
        db.commit()
    return node
