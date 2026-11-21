"""Another site open in the browser can't change the model, and every answer carries the security headers."""


def test_change_from_another_site_is_refused(client):
    response = client.post("/api/nodes", json={"type": "laptop", "name": "x"}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_change_from_the_app_itself_is_allowed(client):
    for origin in ("http://testserver", "http://127.0.0.1:5173", None):
        headers = {"Origin": origin} if origin else {}
        response = client.post("/api/nodes", json={"type": "laptop", "name": f"x-{origin}"}, headers=headers)
        assert response.status_code in (200, 201), response.text


def test_security_headers(client):
    response = client.get("/api/nodes")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
