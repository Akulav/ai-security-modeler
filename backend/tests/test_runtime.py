import asyncio
import hashlib
import json
import zipfile

import httpx
import pytest

from app.services import runtime
from app.services.runtime import RuntimeManager, normalize_model, valid_model_name

MODEL = "hf.co/huihui-ai/Huihui-Qwen3.8-27B-abliterated-GGUF"


def test_names():
    assert normalize_model(MODEL) == f"{MODEL}:latest"
    assert normalize_model("hf.co/a/b:Q4_K_M") == "hf.co/a/b:Q4_K_M"
    assert valid_model_name(MODEL) and valid_model_name("llama3.1:8b")
    for bad in ("", "a b", "../x", "--flag", "a;b"):
        assert not valid_model_name(bad)


def test_checksum_lookup():
    text = f"{'a' * 64}  ./one.zip\n{'b' * 64}  two.zip\n"
    assert runtime._expected_hash(text, "two.zip") == "b" * 64
    assert runtime._expected_hash(text, "one.zip") == "a" * 64
    with pytest.raises(runtime.RuntimeError_):
        runtime._expected_hash(text, "three.zip")


def _manager(handler):
    return RuntimeManager(transport=httpx.MockTransport(handler))


def test_pull_reports_progress_across_layers():
    seen = []

    def handler(request):
        lines = [
            {"status": "pulling manifest"},
            {"status": "pulling", "digest": "a", "total": 100, "completed": 50},
            {"status": "pulling", "digest": "b", "total": 20, "completed": 10},
            {"status": "success"},
        ]
        return httpx.Response(200, text="\n".join(json.dumps(line) for line in lines))

    manager = _manager(handler)
    original = manager._set
    manager._set = lambda *a, **k: (original(*a, **k), seen.append((manager.completed, manager.total)))
    asyncio.run(manager._pull("m"))
    assert (60, 120) in seen


def test_pull_surfaces_errors_sent_inside_the_stream():
    manager = _manager(lambda r: httpx.Response(200, text=json.dumps({"error": "manifest unknown"})))
    with pytest.raises(runtime.RuntimeError_, match="manifest unknown"):
        asyncio.run(manager._pull("m"))


def _install_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "BIN_DIR", tmp_path / "ollama")
    monkeypatch.setattr(runtime, "EXECUTABLE", tmp_path / "ollama" / "ollama.exe")
    monkeypatch.setattr(runtime, "DOWNLOADS_DIR", tmp_path / "downloads")
    monkeypatch.setattr(runtime, "ASSETS", ["bundle.zip"])
    monkeypatch.setattr(runtime.sys, "platform", "win32")


def _bundle(tmp_path) -> bytes:
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("ollama.exe", "binary")
    return path.read_bytes()


def test_install_verifies_extracts_and_skips_next_time(monkeypatch, tmp_path):
    _install_paths(monkeypatch, tmp_path)
    data = _bundle(tmp_path)
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("sha256sum.txt"):
            return httpx.Response(200, text=f"{hashlib.sha256(data).hexdigest()}  ./bundle.zip")
        return httpx.Response(200, content=data)

    manager = _manager(handler)
    asyncio.run(manager._install())
    assert runtime.EXECUTABLE.read_text() == "binary"
    count = len(calls)
    asyncio.run(manager._install())
    assert len(calls) == count


def test_tampered_download_is_rejected_and_not_installed(monkeypatch, tmp_path):
    _install_paths(monkeypatch, tmp_path)
    data = _bundle(tmp_path)

    def handler(request):
        if request.url.path.endswith("sha256sum.txt"):
            return httpx.Response(200, text=f"{'0' * 64}  ./bundle.zip")
        return httpx.Response(200, content=data)

    with pytest.raises(runtime.RuntimeError_, match="checksum"):
        asyncio.run(_manager(handler)._install())
    assert not runtime.EXECUTABLE.exists()
    assert not (runtime.DOWNLOADS_DIR / "bundle.zip.part").exists()


def test_download_resumes_a_partial_file(monkeypatch, tmp_path):
    _install_paths(monkeypatch, tmp_path)
    data = _bundle(tmp_path)
    runtime.DOWNLOADS_DIR.mkdir()
    (runtime.DOWNLOADS_DIR / "bundle.zip.part").write_bytes(data[:10])
    ranges = []

    def handler(request):
        if request.url.path.endswith("sha256sum.txt"):
            return httpx.Response(200, text=f"{hashlib.sha256(data).hexdigest()}  bundle.zip")
        ranges.append(request.headers.get("range"))
        return httpx.Response(206, content=data[10:])

    asyncio.run(_manager(handler)._install())
    assert ranges == ["bytes=10-"]
    assert runtime.EXECUTABLE.exists()


def test_managed_runtime_never_uses_a_server_already_on_the_configured_port(monkeypatch):
    foreign = "http://127.0.0.1:11435"
    monkeypatch.setattr(runtime.settings, "llm_auto_setup", True)
    monkeypatch.setattr(runtime.settings, "ollama_url", foreign)

    async def go():
        manager = RuntimeManager()

        async def skip(_get_selected):
            return None

        manager._bootstrap = skip
        manager.start(lambda: "m")
        await manager._task

    asyncio.run(go())
    assert runtime.settings.ollama_url != foreign


def test_leftover_check_spares_a_process_that_is_not_ours(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "PID_FILE", tmp_path / "ollama.pid")
    monkeypatch.setattr(runtime, "EXECUTABLE", tmp_path / "ollama.exe")
    runtime.PID_FILE.write_text("1234")
    killed = []
    monkeypatch.setattr(runtime, "_kill_tree", killed.append)
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": "C:\\other\\ollama.exe\n"})())
    runtime._stop_leftover()
    assert killed == [] and not runtime.PID_FILE.exists()


def _fake_ollama(installed=("m:latest",), generate_status=200):
    calls = []

    def handler(request):
        path = request.url.path
        if path == "/api/generate":
            calls.append(json.loads(request.content))
            return httpx.Response(generate_status, json={"error": "out of memory"} if generate_status != 200 else {})
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": name} for name in installed]})
        if path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "m:latest", "size": 10, "size_vram": 5}]})
        return httpx.Response(200, json={"version": "1"})

    return handler, calls


def test_load_keeps_the_model_for_the_idle_limit_with_the_analysis_context(monkeypatch):
    monkeypatch.setattr(runtime.settings, "llm_auto_setup", False)
    handler, calls = _fake_ollama()
    manager = _manager(handler)
    manager.idle_seconds = 60

    async def go():
        manager.load("m:latest")
        await manager._task

    asyncio.run(go())
    assert manager.phase == "ready"
    assert calls[0]["keep_alive"] == 60 and calls[0]["options"]["num_ctx"] == runtime.settings.ollama_num_ctx
    assert "prompt" not in calls[0]


def test_no_idle_limit_keeps_the_model_until_unloaded():
    manager = RuntimeManager()
    manager.idle_seconds = 0
    assert manager.keep_alive == -1


def test_changing_the_idle_limit_restarts_a_loaded_models_timer(monkeypatch):
    handler, calls = _fake_ollama()
    manager = _manager(handler)
    asyncio.run(manager.set_idle_seconds(300))
    assert manager.idle_seconds == 300 and calls[0]["model"] == "m:latest" and calls[0]["keep_alive"] == 300


def test_failed_load_reports_the_reason(monkeypatch):
    monkeypatch.setattr(runtime.settings, "llm_auto_setup", False)
    handler, _ = _fake_ollama(generate_status=500)
    manager = _manager(handler)

    async def go():
        manager.load("m:latest")
        await manager._task

    asyncio.run(go())
    assert manager.phase == "error" and "out of memory" in manager.message


def test_unload_frees_models_but_leaves_someone_elses_server_running(monkeypatch):
    monkeypatch.setattr(runtime.settings, "llm_auto_setup", False)
    handler, calls = _fake_ollama()
    manager = _manager(handler)
    manager.phase = "ready"
    asyncio.run(manager.unload())
    assert calls == [{"model": "m:latest", "keep_alive": 0, "options": {"num_ctx": runtime.settings.ollama_num_ctx}}]
    assert manager.phase == "ready"


def test_unload_stops_the_runtime_this_app_started(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime.settings, "llm_auto_setup", True)
    monkeypatch.setattr(runtime, "PID_FILE", tmp_path / "ollama.pid")
    killed = []
    monkeypatch.setattr(runtime, "_kill_tree", killed.append)
    manager = RuntimeManager()
    manager._process = type("P", (), {"pid": 42, "poll": lambda self: None})()
    asyncio.run(manager.unload())
    assert killed == [42] and manager.phase == "stopped" and manager._process is None


def test_status_after_stopping_is_not_an_error(monkeypatch):
    manager = RuntimeManager()
    manager.phase = "stopped"
    status = asyncio.run(manager.status())
    assert status["phase"] == "stopped" and status["available"] is False and status["loaded"] == []


def test_every_chat_restarts_the_idle_timer(monkeypatch):
    from app.services import llm
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "ok"}})

    async def chat():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await llm._chat(client, {"model": "m", "messages": []})

    monkeypatch.setattr(runtime.manager, "idle_seconds", 60)
    asyncio.run(chat())
    monkeypatch.setattr(runtime.manager, "idle_seconds", 0)
    asyncio.run(chat())
    assert sent[0]["keep_alive"] == 60 and sent[1]["keep_alive"] == -1


def test_idle_limit_api_saves_and_validates(client, monkeypatch):
    applied = []

    async def apply(seconds):
        applied.append(seconds)

    monkeypatch.setattr(runtime.manager, "set_idle_seconds", apply)
    assert client.get("/api/llm/status").json()["idle_unload_seconds"] == runtime.manager.idle_seconds
    assert client.post("/api/llm/idle", json={"seconds": -1}).status_code == 422
    assert client.post("/api/llm/idle", json={"seconds": 300}).status_code == 204
    from app.routers import llm as llm_router
    assert applied == [300] and llm_router.stored_idle_seconds() == 300


def test_only_the_launcher_can_quit(client, monkeypatch):
    stopped = []
    monkeypatch.setattr(runtime.manager, "shutdown", lambda: stopped.append(True))
    monkeypatch.setattr(runtime.settings, "launcher_token", "")
    assert client.post("/api/launcher/quit").status_code == 403
    monkeypatch.setattr(runtime.settings, "launcher_token", "secret")
    assert client.post("/api/launcher/quit", headers={"X-Launcher-Token": "wrong"}).status_code == 403
    assert stopped == []
    assert client.post("/api/launcher/quit", headers={"X-Launcher-Token": "secret"}).status_code == 204
    assert stopped == [True]


def test_load_and_retry_routes_can_start_background_work(client, monkeypatch):
    # A fresh manager, since the app's own startup work may still be running on the shared one.
    from app.routers import llm as llm_router
    monkeypatch.setattr(llm_router, "manager", RuntimeManager())
    assert client.post("/api/llm/load").status_code == 202
    monkeypatch.setattr(llm_router, "manager", RuntimeManager())
    assert client.post("/api/llm/retry").status_code == 204


def test_load_and_unload_api_refuse_while_busy(client, monkeypatch):
    def busy(_model):
        raise runtime.RuntimeError_("The LLM is busy.")

    async def busy_unload():
        raise runtime.RuntimeError_("The LLM is busy.")

    monkeypatch.setattr(runtime.manager, "load", busy)
    monkeypatch.setattr(runtime.manager, "unload", busy_unload)
    assert client.post("/api/llm/load").status_code == 409
    assert client.post("/api/llm/unload").status_code == 409


def test_status_and_selection_api(client, monkeypatch):
    status = client.get("/api/llm/status").json()
    assert status["selected"] == f"{MODEL}:latest" == status["default"]
    assert status["available"] is False

    assert client.post("/api/llm/select", json={"model": "bad name"}).status_code == 422
    assert client.post("/api/llm/select", json={"model": "not-downloaded"}).status_code == 422

    async def installed():
        return {"other:latest"}

    monkeypatch.setattr(runtime.manager, "installed_names", installed)
    assert client.post("/api/llm/select", json={"model": "other"}).status_code == 204
    assert client.get("/api/llm/status").json()["selected"] == "other:latest"
