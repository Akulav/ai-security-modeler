"""The Analyze Infrastructure pipeline, streamed to the browser as NDJSON events."""
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..models import AnalysisReport, SavedAnswer
from ..schemas import AnalyzeRequest, AskRequest
from ..services import graph_engine, llm, questions
from ..services.redact import graph_for_llm, mask_text
from ..services.report_pdf import build_report
from .graph import edge_dicts, node_dicts
from .llm import selected_model

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _line(event: dict) -> str:
    return json.dumps(event) + "\n"


def _mask_findings(findings: list[dict]) -> list[dict]:
    # Titles and details quote node names, which could contain an address.
    return [
        {
            "kind": f["kind"], "section": f["section"], "severity": f["severity"],
            "title": mask_text(f["title"]), "detail": mask_text(f["detail"]),
        }
        for f in findings
    ]


@router.post("/finish-research", status_code=204)
def finish_research() -> Response:
    llm.finish_research.set()
    return Response(status_code=204)


@router.get("/latest")
def latest(db: Session = Depends(get_db)):
    report = db.scalar(select(AnalysisReport).order_by(AnalysisReport.created_at.desc()).limit(1))
    if report is None:
        return None
    return {**report.report, "created_at": report.created_at, "model": report.model}


def _saved_answers(db: Session) -> list[SavedAnswer]:
    return list(db.scalars(select(SavedAnswer).order_by(SavedAnswer.created_at.desc())))


def _search_secrets(nodes: list[dict]) -> list[str]:
    secrets = [v for n in nodes for v in (n.get("email"), n.get("ip_address")) if v]
    # Local parts are personal even when the full address is split up in a query.
    return secrets + [n["email"].split("@")[0] for n in nodes if n.get("email") and len(n["email"].split("@")[0]) >= 4]


def _masked_facts(facts: dict) -> dict:
    return {
        "headline": mask_text(facts["headline"]),
        "columns": facts["columns"],
        "rows": [[mask_text(cell) for cell in row["cells"]] for row in facts["rows"]],
    }


def _all_account_names(nodes: list[dict], edges: list[dict]) -> list[str]:
    return [mask_text(row["name"]) for row in questions.account_rows(graph_engine.build_model(nodes, edges))]


@router.get("/questions")
def list_questions(db: Session = Depends(get_db)):
    nodes, edges = node_dicts(db), edge_dicts(db)
    saved = {answer.key: answer for answer in _saved_answers(db)}

    def entry(key: str, label: str, web: bool, facts: dict) -> dict:
        answer = saved.get(key)
        return {
            "id": key, "label": label, "web": web, "facts": facts,
            "answer": answer.answer if answer else None,
            "answered_at": answer.created_at if answer else None,
        }

    return [
        entry(question_id, label, web, questions.question_facts(question_id, nodes, edges))
        for question_id, label, web, _, _ in questions.QUESTIONS
    ]


@router.post("/ask")
async def ask(request: AskRequest, db: Session = Depends(get_db)):
    nodes, edges = node_dicts(db), edge_dicts(db)
    if request.question_id:
        if request.question_id not in questions.BY_ID:
            raise HTTPException(404, "Unknown question")
        key, label, _, instruction, _ = questions.BY_ID[request.question_id]
        facts = questions.question_facts(key, nodes, edges)
    elif request.text:
        key, label = f"custom:{request.text.lower()[:180]}", request.text
        instruction = "Answer the question using the facts below."
        facts = questions.custom_facts(nodes, edges)
    else:
        raise HTTPException(422, "Choose a question or type one")
    model = request.model or selected_model()
    masked = _masked_facts(facts)
    if key == "recent_breaches":
        masked["ALL_ACCOUNTS"] = _all_account_names(nodes, edges)

    async def events() -> AsyncIterator[str]:
        yield _line({"type": "facts", "facts": facts})
        try:
            async for event in llm.stream_answer(
                mask_text(label), instruction, masked, model, request.web_search, _search_secrets(nodes),
            ):
                if event["type"] == "answer":
                    with SessionLocal() as session:
                        session.merge(SavedAnswer(
                            key=key, question=label, answer=event["text"], model=model, created_at=datetime.now(timezone.utc),
                        ))
                        session.commit()
                yield _line(event)
        except llm.LlmError as error:
            yield _line({"type": "llm_error", "message": str(error)})
        yield _line({"type": "done"})

    return StreamingResponse(events(), media_type="application/x-ndjson")


@router.get("/report.pdf")
def report_pdf(db: Session = Depends(get_db)) -> Response:
    saved = db.scalar(select(AnalysisReport).order_by(AnalysisReport.created_at.desc()).limit(1))
    pdf = build_report(
        node_dicts(db), edge_dicts(db),
        narrative=saved.report.get("narrative") if saved else None,
        narrative_date=saved.created_at if saved else None,
        narrative_model=saved.model if saved else None,
        answers=[
            {"question": a.question, "answer": a.answer, "created_at": a.created_at, "model": a.model}
            for a in _saved_answers(db)
        ],
    )
    filename = f"security-report-{datetime.now():%Y-%m-%d}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/run")
async def run(request: AnalyzeRequest, db: Session = Depends(get_db)):
    nodes, edges = node_dicts(db), edge_dicts(db)
    deterministic = graph_engine.analyze(nodes, edges)
    model = request.model or selected_model()
    secrets = _search_secrets(nodes)

    async def events() -> AsyncIterator[str]:
        yield _line({"type": "findings", **deterministic})
        narrative, llm_error = None, None
        if nodes:
            try:
                async for event in llm.stream_analysis(
                    graph_for_llm(nodes, edges), _mask_findings(deterministic["findings"]),
                    model, request.web_search, secrets,
                ):
                    if event["type"] == "report":
                        narrative = event["report"]
                    else:
                        yield _line(event)
            except llm.LlmError as error:
                llm_error = str(error)
                yield _line({"type": "llm_error", "message": llm_error})
            if narrative:
                yield _line({"type": "narrative", "report": narrative, "model": model})

        with SessionLocal() as session:
            session.add(AnalysisReport(
                model=model if narrative else None,
                report={**deterministic, "narrative": narrative, "llm_error": llm_error},
            ))
            session.commit()
        yield _line({"type": "done"})

    return StreamingResponse(events(), media_type="application/x-ndjson")
