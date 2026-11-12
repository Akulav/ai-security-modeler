import json
import tarfile

from app.routers import update
from app.services import runtime


def test_status_reads_what_the_launcher_found(client, monkeypatch, tmp_path):
    monkeypatch.setattr(update, "HOME", tmp_path)
    monkeypatch.setattr(update.settings, "launcher_token", "t")
    assert client.get("/api/update").json()["newer"] is False
    (tmp_path / "update.json").write_text(json.dumps(
        {"current": "0.2.0", "latest": "0.3.0", "newer": True, "notes": "n", "managed": True}))
    body = client.get("/api/update").json()
    assert (body["managed"], body["newer"], body["latest"]) == (True, True, "0.3.0")


def test_check_and_install_leave_a_request_for_the_launcher(client, monkeypatch, tmp_path):
    monkeypatch.setattr(update, "HOME", tmp_path)
    monkeypatch.setattr(update.settings, "launcher_token", "t")
    headers = {"X-Security-Modeler": "1"}
    assert client.post("/api/update/check", headers=headers).status_code == 202
    assert client.post("/api/update/install", headers=headers).status_code == 202
    assert (tmp_path / "update.request").exists() and (tmp_path / "update.apply").exists()


def test_other_pages_and_source_runs_cannot_ask(client, monkeypatch, tmp_path):
    monkeypatch.setattr(update, "HOME", tmp_path)
    monkeypatch.setattr(update.settings, "launcher_token", "t")
    assert client.post("/api/update/install").status_code == 403
    monkeypatch.setattr(update.settings, "launcher_token", "")
    assert client.post("/api/update/install", headers={"X-Security-Modeler": "1"}).status_code == 409
    assert client.get("/api/update").json()["managed"] is False
    assert not (tmp_path / "update.apply").exists()


def test_macs_download_one_archive(monkeypatch):
    monkeypatch.setattr(runtime, "IS_WINDOWS", False)
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    assert runtime._assets() == ["ollama-darwin.tgz"]


def test_the_mac_archive_unpacks(tmp_path):
    source = tmp_path / "ollama"
    source.write_bytes(b"binary")
    archive = tmp_path / "ollama-darwin.tgz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(source, arcname="ollama")
    runtime._extract([archive], tmp_path / "out")
    assert (tmp_path / "out" / "ollama").read_bytes() == b"binary"
