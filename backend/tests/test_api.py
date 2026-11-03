import json

import pytest

from app.services import hibp, llm


def make_node(client, name="N", **fields):
    response = client.post("/api/nodes", json={"type": "online_account", "name": name, **fields})
    assert response.status_code == 201, response.text
    assert response.status_code == 201, response.text
    return response.json()


def test_node_crud_and_validation(client):
    node = make_node(client, email=" a@example.com ", ip_address="")
    assert node["email"] == "a@example.com" and node["ip_address"] is None
    updated = client.patch(f"/api/nodes/{node['id']}", json={"name": "Renamed", "pos_x": 12}).json()
    assert updated["name"] == "Renamed" and updated["pos_x"] == 12 and updated["email"] == "a@example.com"
    assert client.post("/api/nodes", json={"type": "bogus", "name": "x"}).status_code == 422
    assert client.post("/api/nodes", json={"type": "laptop", "name": "x", "email": "nope"}).status_code == 422
    assert client.delete(f"/api/nodes/{node['id']}").status_code == 204
    assert client.get("/api/graph").json()["nodes"] == []


def test_email_can_be_cleared(client):
    node = make_node(client, email="a@example.com")
    assert client.patch(f"/api/nodes/{node['id']}", json={"email": ""}).json()["email"] is None


def test_fields_a_type_does_not_have_are_blanked(client):
    usb = make_node(client, type="usb_drive", ip_address="10.0.0.1", email="a@example.com", os="linux", encryption="none")
    assert usb["ip_address"] is None and usb["email"] is None and usb["os"] is None
    assert usb["encryption"] == "none"
    assert make_node(client, type="laptop", os="ios")["os"] is None
    phone = make_node(client, type="smartphone", os="android", os_version="15")
    assert phone["os"] == "android" and phone["os_version"] == "15"
    changed = client.patch(f"/api/nodes/{phone['id']}", json={"type": "usb_drive"}).json()
    assert changed["os"] is None and changed["os_version"] is None
    assert client.post("/api/nodes", json={"type": "laptop", "name": "x", "os": "beos"}).status_code == 422


def test_defenses_are_stored_and_limited_to_the_type(client):
    app = make_node(client, type="application", defenses=["sms_2fa", "email_2fa", "password", "passkey", "wpa3"])
    assert app["defenses"] == ["sms_2fa", "email_2fa", "password", "passkey"]
    router = make_node(client, type="router", defenses=["firewall", "passkey"], email="a@example.com", ip_address="10.0.0.1")
    assert router["defenses"] == ["firewall"] and router["email"] is None and router["ip_address"] == "10.0.0.1"
    assert client.patch(f"/api/nodes/{router['id']}", json={"defenses": []}).json()["defenses"] == []
    tv = make_node(client, type="smart_tv", os="webos", encryption="none")
    assert tv["os"] == "webos" and tv["encryption"] == "unknown"
    local = make_node(client, type="local_server_account", email="a@example.com")
    assert local["email"] is None
    response = client.post("/api/edges", json={"source_id": local["id"], "target_id": tv["id"], "relation": "account_on"})
    assert response.status_code == 201


def _link(client, source, target, relation):
    return client.post("/api/edges", json={"source_id": source["id"], "target_id": target["id"], "relation": relation})


@pytest.mark.parametrize("first,second", [("stores_credentials", "provides_totp"), ("provides_totp", "stores_credentials")])
def test_password_and_totp_links_combine_into_one(client, first, second):
    vault, site = make_node(client, type="password_manager"), make_node(client)
    original = _link(client, vault, site, first).json()
    response = _link(client, vault, site, second)
    assert response.status_code == 201 and response.json()["relation"] == "stores_credentials_totp"
    assert [e["relation"] for e in client.get("/api/graph").json()["edges"]] == ["stores_credentials_totp"]
    assert _link(client, vault, site, first).status_code == 409
    assert response.json()["id"] in (original["id"], response.json()["id"])

    radius = client.get(f"/api/nodes/{vault['id']}/blast-radius").json()
    assert radius["loss"] == [site["id"]] and radius["compromise"] == [site["id"]]


def test_combining_keeps_settings_and_leaves_other_pairs_alone(client):
    vault, a, b = make_node(client, type="password_manager"), make_node(client, "A"), make_node(client, "B")
    edge = _link(client, vault, a, "stores_credentials").json()
    client.patch(f"/api/edges/{edge['id']}", json={"loss_mode": "alternative", "notes": "kept"})
    combined = _link(client, vault, a, "provides_totp").json()
    assert combined["loss_mode"] == "alternative" and combined["notes"] == "kept"
    assert _link(client, vault, b, "stores_credentials").json()["relation"] == "stores_credentials"
    split = client.patch(f"/api/edges/{combined['id']}", json={"relation": "provides_totp"}).json()
    assert split["relation"] == "provides_totp"


def test_importing_both_links_combines_them(client):
    graph = {
        "nodes": [{"id": "v", "type": "password_manager", "name": "V"}, {"id": "s", "type": "online_account", "name": "S"}],
        "edges": [{"source_id": "v", "target_id": "s", "relation": "provides_totp"},
                  {"source_id": "v", "target_id": "s", "relation": "stores_credentials"}],
    }
    assert [e["relation"] for e in client.post("/api/import", json=graph).json()["edges"]] == ["stores_credentials_totp"]


def _edges(client):
    return [(e["source_id"], e["target_id"], e["relation"]) for e in client.get("/api/graph").json()["edges"]]


def test_adding_an_email_node_connects_accounts_using_that_address(client):
    netflix = make_node(client, "Netflix", type="entertainment_account", email="Me@Example.com")
    github = make_node(client, "GitHub", email="me@example.com")
    make_node(client, "Other", email="someone@example.com")
    vault = make_node(client, "Vault", type="password_manager", email="me@example.com")
    mail = make_node(client, "Mail", type="email_account", email="me@example.com")
    assert set(_edges(client)) == {
        (mail["id"], netflix["id"], "can_reset_password"), (mail["id"], github["id"], "can_reset_password"),
    }
    assert vault["id"] not in {target for _, target, _ in _edges(client)}


def test_entering_an_address_links_from_either_side_and_only_on_a_change(client):
    mail = make_node(client, "Mail", type="email_account")
    site = make_node(client, "Site", email="me@example.com")
    assert _edges(client) == []
    client.patch(f"/api/nodes/{mail['id']}", json={"email": "me@example.com"})
    assert _edges(client) == [(mail["id"], site["id"], "can_reset_password")]

    late = make_node(client, "Late")
    client.patch(f"/api/nodes/{late['id']}", json={"email": "ME@example.com"})
    assert (mail["id"], late["id"], "can_reset_password") in _edges(client)

    edge_id = next(e["id"] for e in client.get("/api/graph").json()["edges"] if e["target_id"] == site["id"])
    client.delete(f"/api/edges/{edge_id}")
    client.patch(f"/api/nodes/{mail['id']}", json={"name": "Renamed", "email": "me@example.com"})
    assert (mail["id"], site["id"], "can_reset_password") not in _edges(client)


def test_email_link_is_not_doubled_and_import_adds_none(client):
    mail = make_node(client, "Mail", type="email_account")
    site = make_node(client, "Site", email="me@example.com")
    _link(client, mail, site, "recovery_for")
    client.patch(f"/api/nodes/{mail['id']}", json={"email": "me@example.com"})
    assert [relation for _, _, relation in _edges(client)] == ["recovery_for"]
    exported = client.get("/api/export").json()
    exported["edges"] = []
    assert client.post("/api/import", json=exported).json()["edges"] == []


def test_infrastructure_account_behaves_like_an_account(client):
    cloudflare = make_node(client, "Cloudflare", type="infrastructure_account", email="a@example.com", defenses=["totp"])
    assert cloudflare["email"] == "a@example.com" and cloudflare["defenses"] == ["totp"]
    vault = make_node(client, type="password_manager")
    assert _link(client, vault, cloudflare, "stores_credentials").status_code == 201


def test_password_manager_blast_radius(client):
    vault = make_node(client, "Vault", type="password_manager", email="a@example.com", ip_address="10.0.0.1")
    assert vault["email"] == "a@example.com" and vault["ip_address"] is None
    bank = make_node(client, "Bank", type="financial_account")
    client.post("/api/edges", json={"source_id": vault["id"], "target_id": bank["id"], "relation": "stores_credentials"})
    radius = client.get(f"/api/nodes/{vault['id']}/blast-radius").json()
    assert radius["loss"] == [bank["id"]] and radius["compromise"] == [bank["id"]]


def test_nonsense_relationships_are_rejected(client):
    usb, bank = make_node(client, type="usb_drive"), make_node(client, type="financial_account")
    response = client.post("/api/edges", json={"source_id": usb["id"], "target_id": bank["id"], "relation": "provides_2fa_sms"})
    assert response.status_code == 422 and "can't be" in response.json()["detail"]
    phone = make_node(client, type="smartphone")
    edge = client.post("/api/edges", json={"source_id": phone["id"], "target_id": bank["id"], "relation": "provides_2fa_sms"}).json()
    assert client.patch(f"/api/edges/{edge['id']}", json={"relation": "stored_on"}).status_code == 422


def test_apps_node_lists_apps_that_depend_on_the_device(client):
    phone = make_node(client, "Phone", type="smartphone")
    apps = make_node(client, "Apps", type="app_group")
    client.post("/api/edges", json={"source_id": apps["id"], "target_id": phone["id"], "relation": "installed_on"})
    authy = make_node(client, "Authy", type="application", parent_id=apps["id"])
    github = make_node(client, "GitHub")
    client.post("/api/edges", json={"source_id": authy["id"], "target_id": github["id"], "relation": "provides_totp"})

    radius = client.get(f"/api/nodes/{phone['id']}/blast-radius").json()
    assert set(radius["loss"]) == {authy["id"], github["id"]}
    assert client.post("/api/nodes", json={"type": "laptop", "name": "x", "parent_id": apps["id"]}).status_code == 422

    round_trip = client.post("/api/import", json=client.get("/api/export").json()).json()
    names = {n["id"]: n["name"] for n in round_trip["nodes"]}
    assert [names[n["parent_id"]] for n in round_trip["nodes"] if n["parent_id"]] == ["Apps"]

    client.delete(f"/api/nodes/{[i for i, n in names.items() if n == 'Apps'][0]}")
    assert sorted(n["name"] for n in client.get("/api/graph").json()["nodes"]) == ["GitHub", "Phone"]


def test_old_os_nodes_become_the_device_os_field(client):
    graph = {
        "nodes": [
            {"id": "phone", "type": "smartphone", "name": "Phone"},
            {"id": "os", "type": "os", "name": "iOS 17"},
            {"id": "app", "type": "application", "name": "Authy"},
        ],
        "edges": [
            {"source_id": "os", "target_id": "phone", "relation": "installed_on"},
            {"source_id": "app", "target_id": "os", "relation": "runs_on"},
        ],
    }
    result = client.post("/api/import", json=graph).json()
    by_name = {n["name"]: n for n in result["nodes"]}
    assert set(by_name) == {"Phone", "Authy"}
    assert by_name["Phone"]["os"] == "ios" and by_name["Phone"]["os_version"] == "17"
    assert [(e["source_id"], e["target_id"]) for e in result["edges"]] == [(by_name["Authy"]["id"], by_name["Phone"]["id"])]


def test_edges_validate_and_cascade(client):
    a, b = make_node(client, "A", type="application"), make_node(client, "B")
    payload = {"source_id": a["id"], "target_id": b["id"], "relation": "provides_totp"}
    edge = client.post("/api/edges", json=payload).json()
    assert client.post("/api/edges", json=payload).status_code == 409
    assert client.post("/api/edges", json={**payload, "target_id": a["id"]}).status_code == 422
    assert client.post("/api/edges", json={**payload, "relation": "bogus"}).status_code == 422
    assert client.post("/api/edges", json={**payload, "target_id": "missing"}).status_code == 404

    changed = client.patch(f"/api/edges/{edge['id']}", json={"loss_mode": "alternative"}).json()
    assert changed["loss_mode"] == "alternative"
    reset = client.patch(f"/api/edges/{edge['id']}", json={"loss_mode": None}).json()
    assert reset["loss_mode"] is None

    client.delete(f"/api/nodes/{a['id']}")
    assert client.get("/api/graph").json()["edges"] == []


def test_blast_radius_endpoint(client):
    a, b = make_node(client, "A", type="application"), make_node(client, "B")
    client.post("/api/edges", json={"source_id": a["id"], "target_id": b["id"], "relation": "provides_totp"})
    radius = client.get(f"/api/nodes/{a['id']}/blast-radius").json()
    assert radius["loss"] == [b["id"]] and radius["compromise"] == [] and radius["dependents"] == [b["id"]]


def test_export_import_round_trip_and_rejects_bad_files(client):
    a, b = make_node(client, "A", email="a@example.com"), make_node(client, "B")
    client.post("/api/edges", json={"source_id": a["id"], "target_id": b["id"], "relation": "sso_for"})
    exported = client.get("/api/export").json()

    bad = {"nodes": exported["nodes"], "edges": [{**exported["edges"][0], "target_id": "missing"}]}
    assert client.post("/api/import", json=bad).status_code == 422
    assert len(client.get("/api/graph").json()["nodes"]) == 2

    graph = client.post("/api/import", json=exported).json()
    assert sorted(n["name"] for n in graph["nodes"]) == ["A", "B"]
    assert len(graph["edges"]) == 1


def test_seed_only_loads_into_empty_graph(client):
    assert len(client.post("/api/seed").json()["nodes"]) > 5
    assert client.post("/api/seed").status_code == 409


def _fake_breaches(monkeypatch, result):
    async def fake(email):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(hibp, "check_email", fake)


BREACH = {"name": "Adobe", "data_classes": ["Passwords"], "description": "d", "domain": "adobe.com"}


def test_breach_check_stores_result_and_editing_email_clears_it(client, monkeypatch):
    node = make_node(client, email="a@example.com")
    _fake_breaches(monkeypatch, [BREACH])
    checked = client.post(f"/api/hibp/check/{node['id']}").json()
    assert checked["breaches"][0]["name"] == "Adobe"
    assert "Change the password" in checked["breach_advice"]

    same = client.patch(f"/api/nodes/{node['id']}", json={"email": "a@example.com"}).json()
    assert same["breaches"]
    changed = client.patch(f"/api/nodes/{node['id']}", json={"email": "b@example.com"}).json()
    assert changed["breaches"] is None and changed["breach_advice"] is None


def test_breach_check_errors(client, monkeypatch):
    without = make_node(client)
    assert client.post(f"/api/hibp/check/{without['id']}").status_code == 422
    node = make_node(client, email="a@example.com")
    _fake_breaches(monkeypatch, hibp.HibpError("rate limited", 429))
    response = client.post(f"/api/hibp/check/{node['id']}")
    assert response.status_code == 429 and response.json()["detail"] == "rate limited"
    assert client.get("/api/graph").json()["nodes"][1]["breach_checked_at"] is None


def test_advice_keeps_fallback_when_ollama_is_down(client, monkeypatch):
    node = make_node(client, email="a@example.com")
    _fake_breaches(monkeypatch, [BREACH])
    client.post(f"/api/hibp/check/{node['id']}")
    response = client.post(f"/api/hibp/advice/{node['id']}")
    assert response.status_code == 503
    stored = client.get("/api/graph").json()["nodes"][0]
    assert "Change the password" in stored["breach_advice"]


def test_analysis_still_returns_findings_when_ollama_is_down(client):
    client.post("/api/seed")
    response = client.post("/api/analysis/run", json={"web_search": False})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["type"] == "findings" and events[0]["findings"]
    assert any(e["type"] == "llm_error" and "isn't running" in e["message"] for e in events)
    assert events[-1]["type"] == "done"
    latest = client.get("/api/analysis/latest").json()
    assert latest["findings"] and latest["narrative"] is None


def test_nothing_sent_to_the_llm_contains_an_address(client, monkeypatch):
    make_node(client, "alex@example.com", email="alex@example.com", ip_address="10.1.2.3",
              security_level="critical", password_type="reused")
    sent = {}

    async def fake_stream(graph, findings, model, allow_web, secrets):
        sent["payload"] = json.dumps([graph, findings])
        yield {"type": "report", "report": {"summary": "s"}}

    monkeypatch.setattr(llm, "stream_analysis", fake_stream)
    client.post("/api/analysis/run", json={"web_search": False})
    assert sent["payload"] and "alex@" not in sent["payload"] and "10.1.2.3" not in sent["payload"]


def test_foreign_host_header_is_rejected(client):
    assert client.get("/api/graph", headers={"host": "evil.example"}).status_code == 400


@pytest.mark.parametrize("origin,allowed", [("http://127.0.0.1:5173", True), ("https://evil.example", False)])
def test_cors_only_allows_the_dev_frontend(client, origin, allowed):
    response = client.get("/api/graph", headers={"origin": origin})
    assert ("access-control-allow-origin" in response.headers) is allowed
