import json
from io import BytesIO

from pypdf import PdfReader

from app.services import llm
from app.services.graph_engine import build_model
from app.services.questions import QUESTIONS, account_rows, question_facts
from app.services.report_pdf import build_report


def node(node_id, node_type="online_account", level="medium", password="unknown", **extra):
    return {"id": node_id, "type": node_type, "name": node_id, "security_level": level,
            "password_type": password, "status": "active", **extra}


def edge(source, target, relation):
    return {"id": f"{source}-{target}", "source_id": source, "target_id": target, "relation": relation, "loss_mode": None}


NODES = [
    node("strong", defenses=["password", "hardware_key"], password="manager"),
    node("totp", defenses=["password", "totp"], password="manager"),
    node("sms", "financial_account", "critical", defenses=["password", "sms_2fa"]),
    node("bare", defenses=["password"], password="reused"),
    node("unknown"),
    node("drawn", password="manager"),
    node("old", status="legacy", defenses=["password"]),
    node("phone", "smartphone"),
    node("authy", "application"),
]
EDGES = [edge("authy", "drawn", "provides_totp")]


def names(question):
    return [row["cells"][0] for row in question_facts(question, NODES, EDGES)["rows"]]


def test_scores_rank_strength_and_count_drawn_links():
    rows = {r["name"]: r for r in account_rows(build_model(NODES, EDGES))}
    assert rows["strong"]["score"] > rows["totp"]["score"] > rows["sms"]["score"] > rows["bare"]["score"]
    assert rows["drawn"]["factors"] == ["totp"]
    assert rows["unknown"]["recorded"] is False


def test_no_2fa_separates_known_from_unrecorded():
    rows = question_facts("no_2fa", NODES, EDGES)["rows"]
    state = {r["cells"][0]: r["cells"][2] for r in rows}
    assert state["bare"] == "No 2FA" and state["unknown"] == "Not recorded"
    assert "totp" not in state and "drawn" not in state


def test_list_questions():
    assert "drawn" not in names("totp_candidates") and "sms" in names("totp_candidates")
    assert "strong" not in names("totp_candidates")
    assert names("weak_2fa") == ["sms"]
    assert names("weak_passwords") == ["bare"]
    assert names("delete_list") == ["old"]
    assert "unknown" not in names("least_protected")
    assert "phone" in names("devices")


def test_every_question_builds_on_an_empty_map_and_the_sample(client):
    for question_id, *_ in QUESTIONS:
        assert question_facts(question_id, [], [])["rows"] == []
    client.post("/api/seed")
    listed = client.get("/api/analysis/questions").json()
    assert len(listed) == len(QUESTIONS) and all(q["facts"]["headline"] for q in listed)


def _fake_answer(monkeypatch, sent):
    async def fake(question, instruction, facts, model, allow_web, secrets):
        sent["payload"] = json.dumps([question, instruction, facts])
        yield {"type": "answer", "text": "Fix **this** first."}

    monkeypatch.setattr(llm, "stream_answer", fake)


def test_asking_streams_facts_saves_the_answer_and_hides_addresses(client, monkeypatch):
    client.post("/api/nodes", json={"type": "online_account", "name": "alex@example.com", "email": "alex@example.com"})
    sent = {}
    _fake_answer(monkeypatch, sent)
    response = client.post("/api/analysis/ask", json={"question_id": "no_2fa", "web_search": False})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["type"] == "facts" and events[1]["text"] == "Fix **this** first." and events[-1]["type"] == "done"
    assert "alex@" not in sent["payload"]
    saved = {q["id"]: q for q in client.get("/api/analysis/questions").json()}
    assert saved["no_2fa"]["answer"] == "Fix **this** first."


def test_custom_question_and_bad_requests(client, monkeypatch):
    sent = {}
    _fake_answer(monkeypatch, sent)
    assert client.post("/api/analysis/ask", json={"question_id": "nope"}).status_code == 404
    assert client.post("/api/analysis/ask", json={}).status_code == 422
    response = client.post("/api/analysis/ask", json={"text": "Is Steam safe?", "web_search": False})
    assert response.status_code == 200 and "Is Steam safe?" in sent["payload"]


def test_ollama_down_reports_an_error_and_saves_nothing(client):
    response = client.post("/api/analysis/ask", json={"question_id": "spof", "web_search": False})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert any(e["type"] == "llm_error" for e in events) and events[-1]["type"] == "done"
    assert all(q["answer"] is None for q in client.get("/api/analysis/questions").json())


def _pdf_text(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_pdf_contains_the_report_and_no_addresses():
    nodes = [
        *NODES,
        node("mail", "email_account", email="secret.person@example.com", defenses=["password"]),
        node("pc", "desktop", ip_address="10.20.30.40", os="linux", os_version="24.04"),
        node("router", "router"),
    ]
    narrative = {"summary": "Your phone is key.", "vulnerabilities": [{"title": "AI risk", "detail": "d", "severity": "high"}]}
    answers = [{"question": "Which accounts don't use 2FA?", "answer": "- Fix <b>bare</b> & **old**", "created_at": None}]
    data = build_report(nodes, EDGES, narrative=narrative, answers=answers)
    assert data.startswith(b"%PDF")
    text = _pdf_text(data)
    for expected in ("Personal Security", "Your phone is key", "AI risk", "use 2FA", "Fix <b>bare</b>", "Every account", "24.04", "router"):
        assert expected in text, expected
    assert "secret.person" not in text and "10.20.30.40" not in text


def test_pdf_builds_for_an_empty_map_and_the_endpoint_downloads(client):
    assert build_report([], []).startswith(b"%PDF")
    client.post("/api/seed")
    response = client.get("/api/analysis/report.pdf")
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert "No AI analysis" in _pdf_text(response.content)
