"""Portable LLM runtime: downloads Ollama into the data folder, runs it, and manages models.

Everything lives under llm/ (binaries, models, Ollama's home) and it runs on a free port chosen
at startup, so it can't clash with an Ollama already on the system. Deleting that folder
removes it completely.
"""
import asyncio
import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import httpx

from ..config import DATA_ROOT, settings

LLM_DIR = DATA_ROOT / "llm"
BIN_DIR = LLM_DIR / "ollama"
MODELS_DIR = LLM_DIR / "models"
HOME_DIR = LLM_DIR / "home"
DOWNLOADS_DIR = LLM_DIR / "downloads"
LOG_FILE = LLM_DIR / "ollama.log"
PID_FILE = LLM_DIR / "ollama.pid"
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
# The Windows zip and the macOS archive have the program at their top; the Linux archive has it under bin/.
EXECUTABLE = BIN_DIR / "ollama.exe" if IS_WINDOWS else BIN_DIR / "ollama" if IS_MAC else BIN_DIR / "bin" / "ollama"
LINUX_ARCHITECTURES = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


def _has_amd_gpu() -> bool:
    return any(
        path.read_text().strip() == "0x1002"  # AMD's PCI vendor id.
        for path in Path("/sys/class/drm").glob("card*/device/vendor")
        if path.is_file()
    )


def _assets() -> list[str]:
    if IS_WINDOWS:
        # The ROCm add-on is small and enables AMD GPUs; Ollama ignores it on other hardware.
        return ["ollama-windows-amd64.zip", "ollama-windows-amd64-rocm.zip"]
    if sys.platform == "darwin":
        # One archive for Apple Silicon and Intel Macs; it uses Metal on Apple Silicon.
        return ["ollama-darwin.tgz"]
    architecture = LINUX_ARCHITECTURES.get(platform.machine().lower())
    if sys.platform != "linux" or architecture is None:
        return []
    # On Linux the ROCm add-on is about 1 GB, so it's only fetched where it can be used.
    return [f"ollama-linux-{architecture}.tar.zst"] + (
        [f"ollama-linux-{architecture}-rocm.tar.zst"] if architecture == "amd64" and _has_amd_gpu() else []
    )


ASSETS = _assets()
MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][\w.\-/]*(:[\w.\-]+)?$")
STARTUP_SECONDS = 30
CHUNK_BYTES = 1024 * 1024


class RuntimeError_(Exception):
    pass


def normalize_model(name: str) -> str:
    """Ollama reports untagged models as name:latest, so compare them in that form."""
    name = name.strip()
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"


def valid_model_name(name: str) -> bool:
    return len(name) <= 200 and bool(MODEL_NAME_RE.match(name.strip()))


def _expected_hash(checksums: str, asset: str) -> str:
    for line in checksums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*").removeprefix("./") == asset:
            return parts[0].lower()
    raise RuntimeError_(f"No published checksum for {asset}")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _kill_tree(pid: int) -> None:
    """Ends the runtime and the model runner processes it spawned."""
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, check=False)
        return
    # On Linux it's started as the leader of its own process group, so the group is the tree.
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _end_with_parent() -> None:
    """Runs in the Linux child before it starts: the kernel stops it if this app dies, as the
    Windows job does. Best effort, since it needs glibc."""
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # 1 is PR_SET_PDEATHSIG.
    except OSError:
        pass


def _process_path(pid: int) -> str:
    """The program a running process was started from, or an empty string."""
    if IS_MAC:
        result = subprocess.run(["ps", "-o", "comm=", "-p", str(pid)], capture_output=True, text=True, check=False)
        return result.stdout.strip()
    if not IS_WINDOWS:
        try:
            return os.readlink(f"/proc/{pid}/exe")
        except OSError:
            return ""
    # A direct call rather than PowerShell, which writes caches of its own into the user's profile.
    kernel32 = _kernel32()
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    process = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not process:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_uint32(len(buffer))
        ok = kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size))
        return buffer.value if ok else ""
    finally:
        kernel32.CloseHandle(process)


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32), ("SchedulingClass", ctypes.c_uint32),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits), ("IoInfo", ctypes.c_uint64 * 6),
        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_EXTENDED_LIMIT_INFORMATION = 9
_KILL_ON_JOB_CLOSE = 0x2000
_job: int | None = None


def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.IsProcessInJob.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    return kernel32


def _close_children_with_app() -> None:
    """Puts this app in a Windows job that ends when its process does, however it ends: Ctrl+C,
    closing its window, or a crash. Processes it starts afterwards, such as the runtime and its
    model runners, join the job as they start, so they end with it. Call it before starting them.
    Best effort: if it fails, shutdown() and the leftover check on the next start still apply."""
    global _job
    if _job is not None or sys.platform != "win32":
        return
    kernel32 = _kernel32()
    job = kernel32.CreateJobObjectW(None, None)
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
    if (
        job
        and kernel32.SetInformationJobObject(job, _EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits))
        and kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess())
    ):
        # Never closed here: Windows closes it as this process exits, which is what ends the job.
        _job = job


def _keep_in_job(pid: int) -> None:
    """Adds a process that left the job as it started. Some launchers (IDE terminals, sandboxes)
    run the app in a job of their own that lets every child break away, which would leave it out."""
    if _job is None:
        return
    kernel32 = _kernel32()
    process = kernel32.OpenProcess(0x1000 | 0x0100 | 0x0001, False, pid)  # Query, set quota, terminate.
    if not process:
        return
    inside = ctypes.c_int()
    if kernel32.IsProcessInJob(process, _job, ctypes.byref(inside)) and not inside.value:
        kernel32.AssignProcessToJobObject(_job, process)
    kernel32.CloseHandle(process)


def _stop_leftover() -> None:
    """Stops this runtime if a crashed session left it running. The path check matters: Windows
    reuses process ids, and the old id could now belong to something else."""
    try:
        pid = int(PID_FILE.read_text())
    except (OSError, ValueError):
        return
    running = _process_path(pid)
    if running and os.path.normcase(running) == os.path.normcase(str(EXECUTABLE)):
        _kill_tree(pid)
    PID_FILE.unlink(missing_ok=True)


def _extract(archives: list[Path], destination: Path) -> None:
    # Extracted beside the destination and renamed last, so a half-finished install never counts.
    temporary = destination.with_name(destination.name + ".tmp")
    shutil.rmtree(temporary, ignore_errors=True)
    for archive in archives:
        if archive.name.endswith(".tar.zst"):
            import zstandard  # Installed on Linux only, the one platform whose archives use it.

            with archive.open("rb") as raw, zstandard.ZstdDecompressor().stream_reader(raw) as stream:
                with tarfile.open(fileobj=stream, mode="r|") as bundle:
                    # "data" refuses paths outside the folder, links out of it and special files.
                    bundle.extractall(temporary, filter="data")
        elif archive.name.endswith(".tgz"):
            with tarfile.open(archive, mode="r:gz") as bundle:
                bundle.extractall(temporary, filter="data")
        else:
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(temporary)
    # (should a macOS archive ever put the program under bin/ as the Linux one does)
    if IS_MAC and not (temporary / "ollama").exists() and (temporary / "bin" / "ollama").exists():
        (temporary / "ollama").symlink_to(Path("bin") / "ollama")
    shutil.rmtree(destination, ignore_errors=True)
    temporary.rename(destination)


class RuntimeManager:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport
        self.phase = "idle"  # idle, installing, starting, pulling, loading, ready, stopped, offline, error
        self.message = ""
        self.completed = 0
        self.total = 0
        self.pulling_model: str | None = None
        # How long the model stays in memory after its last request. 0 means until it's unloaded.
        self.idle_seconds = settings.llm_idle_unload_seconds
        self._process: subprocess.Popen | None = None
        self._task: asyncio.Task | None = None

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def keep_alive(self) -> int:
        """What every request tells Ollama, which then frees the model once it's been idle that long."""
        return self.idle_seconds if self.idle_seconds > 0 else -1

    async def set_idle_seconds(self, seconds: int) -> None:
        """Changes the idle limit, including for a model already in memory, whose timer restarts."""
        self.idle_seconds = seconds
        for model in await self.loaded():
            await self._keep_alive(model["name"], self.keep_alive)

    def _client(self, **kwargs) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport, **kwargs)

    def _set(self, phase: str, message: str = "", completed: int = 0, total: int = 0) -> None:
        self.phase, self.message, self.completed, self.total = phase, message, completed, total

    def start(self, get_selected) -> None:
        """Begins setup in the background, so the app is usable while it runs. Safe to call again."""
        if self.busy:
            return
        # A port of its own from the start: anything else on the machine, such as an Ollama the
        # user already runs, must never be mistaken for this runtime or sent the user's graph.
        if settings.llm_auto_setup and not self._alive():
            settings.ollama_url = f"http://127.0.0.1:{_free_port()}"
        self._task = asyncio.create_task(self._bootstrap(get_selected))

    def _alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def pull(self, model: str, on_success) -> None:
        if self.busy:
            raise RuntimeError_("Another download is already running")

        async def work():
            await self._pull(model)
            on_success()

        self._task = asyncio.create_task(self._guarded(work()))

    def load(self, model: str) -> None:
        """Starts the runtime if needed and puts the model in memory, where it stays while in use."""
        if self.busy:
            raise RuntimeError_("The LLM is busy. Try again when it finishes.")
        if settings.llm_auto_setup and not self._alive():
            settings.ollama_url = f"http://127.0.0.1:{_free_port()}"

        async def work():
            if settings.llm_auto_setup:
                await self._install()
                await self._serve()
            if model not in await self.installed_names():
                await self._pull(model)
            self._set("loading", f"Loading {model} into memory")
            await self._keep_alive(model, self.keep_alive)

        self._task = asyncio.create_task(self._guarded(work()))

    async def unload(self) -> None:
        """Frees the model's memory. A runtime this app started is stopped too, which frees the rest."""
        if self.busy:
            raise RuntimeError_("The LLM is busy. Try again when it finishes.")
        if settings.llm_auto_setup:
            if self._alive():
                await asyncio.to_thread(_kill_tree, self._process.pid)
                PID_FILE.unlink(missing_ok=True)
            self._process = None
            self._set("stopped")
            return
        # Another program's server: free the models, but leave it running.
        for model in await self.loaded():
            await self._keep_alive(model["name"], 0)

    async def _keep_alive(self, model: str, keep_alive: int) -> None:
        # A generate request with no prompt only loads or unloads. The context size must match
        # what analysis uses, or the first analysis would reload the model.
        payload = {"model": model, "keep_alive": keep_alive, "options": {"num_ctx": settings.ollama_num_ctx}}
        async with self._client(timeout=httpx.Timeout(None, connect=10)) as client:
            response = await client.post(f"{settings.ollama_url}/api/generate", json=payload)
        if response.status_code != 200:
            raise RuntimeError_(_ollama_error(response.text, model))

    async def loaded(self) -> list[dict]:
        try:
            async with self._client(timeout=5) as client:
                response = await client.get(f"{settings.ollama_url}/api/ps")
                response.raise_for_status()
        except httpx.HTTPError:
            return []
        return [
            {"name": m["name"], "size": m.get("size", 0), "size_vram": m.get("size_vram", 0)}
            for m in response.json().get("models", [])
        ]

    def cancel(self) -> None:
        if self.busy:
            self._task.cancel()

    async def _guarded(self, work) -> None:
        try:
            await work
            self._set("ready")
        except asyncio.CancelledError:
            self._set("ready", "Download paused. Starting it again resumes where it stopped.")
        except (RuntimeError_, httpx.HTTPError, OSError, zipfile.BadZipFile) as error:
            self._set("error", str(error) or type(error).__name__)
        finally:
            self.pulling_model = None

    async def _bootstrap(self, get_selected) -> None:
        async def work():
            if settings.llm_auto_setup:
                await self._install()
                await self._serve()
                selected = get_selected()
                if selected not in await self.installed_names():
                    await self._pull(selected)
            elif not await self.reachable():
                raise RuntimeError_(f"No Ollama server at {settings.ollama_url}")

        await self._guarded(work())

    async def _install(self) -> None:
        version_file = BIN_DIR / "VERSION"
        if EXECUTABLE.exists() and version_file.exists() and version_file.read_text().strip() == settings.ollama_version:
            return
        if not ASSETS:
            raise RuntimeError_(
                f"Automatic setup supports Windows, macOS and Linux on x86-64 or ARM64, not {sys.platform} on "
                f"{platform.machine()}. Set LLM_AUTO_SETUP=false and run Ollama yourself."
            )

        base = f"https://github.com/ollama/ollama/releases/download/{settings.ollama_version}"
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        timeout = httpx.Timeout(60, connect=15)
        async with self._client(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(f"{base}/sha256sum.txt")
            response.raise_for_status()
            checksums = response.text
            archives = []
            for asset in ASSETS:
                archives.append(await self._download(client, f"{base}/{asset}", asset, _expected_hash(checksums, asset)))

        self._set("installing", "Unpacking the LLM runtime")
        await asyncio.to_thread(_extract, archives, BIN_DIR)
        version_file.write_text(settings.ollama_version)
        shutil.rmtree(DOWNLOADS_DIR, ignore_errors=True)

    async def _download(self, client: httpx.AsyncClient, url: str, asset: str, expected: str) -> Path:
        target = DOWNLOADS_DIR / asset
        partial = DOWNLOADS_DIR / f"{asset}.part"
        if target.exists() and await asyncio.to_thread(_file_sha256, target) == expected:
            return target

        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        async with client.stream("GET", url, headers=headers) as response:
            if response.status_code == 416:
                partial.unlink()
                raise RuntimeError_("The partial download was invalid. Press Retry.")
            response.raise_for_status()
            resumed = response.status_code == 206
            done = offset if resumed else 0
            total = done + int(response.headers.get("content-length", 0))
            with partial.open("ab" if resumed else "wb") as handle:
                async for chunk in response.aiter_bytes(CHUNK_BYTES):
                    handle.write(chunk)
                    done += len(chunk)
                    self._set("installing", f"Downloading {asset}", done, total)

        self._set("installing", f"Verifying {asset}")
        if await asyncio.to_thread(_file_sha256, partial) != expected:
            partial.unlink()
            raise RuntimeError_(f"{asset} failed its checksum and was deleted. Press Retry.")
        partial.replace(target)
        return target

    async def _serve(self) -> None:
        self._set("starting", "Starting the LLM runtime")
        if self._alive():
            return
        await asyncio.to_thread(_stop_leftover)
        for folder in (MODELS_DIR, HOME_DIR):
            folder.mkdir(parents=True, exist_ok=True)
        host = settings.ollama_url.split("://", 1)[-1].rstrip("/")
        env = {
            **os.environ,
            "OLLAMA_HOST": host,
            "OLLAMA_MODELS": str(MODELS_DIR),
            "HOME": str(HOME_DIR),
            "USERPROFILE": str(HOME_DIR),
        }
        _close_children_with_app()
        log = LOG_FILE.open("ab")
        platform_options = (
            {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if IS_WINDOWS
            else {"start_new_session": True, "preexec_fn": _end_with_parent}
        )
        self._process = subprocess.Popen(
            [str(EXECUTABLE), "serve"], env=env, cwd=BIN_DIR, stdout=log, stderr=log, **platform_options,
        )
        log.close()
        _keep_in_job(self._process.pid)
        PID_FILE.write_text(str(self._process.pid))
        for _ in range(STARTUP_SECONDS * 2):
            if not self._alive():
                break
            if await self.reachable():
                return
            await asyncio.sleep(0.5)
        raise RuntimeError_(f"The LLM runtime didn't start. See {LOG_FILE}")

    async def _pull(self, model: str) -> None:
        self.pulling_model = model
        self._set("pulling", f"Connecting to download {model}")
        layers: dict[str, tuple[int, int]] = {}
        timeout = httpx.Timeout(None, connect=10)
        async with self._client(timeout=timeout) as client:
            async with client.stream("POST", f"{settings.ollama_url}/api/pull", json={"model": model}) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise RuntimeError_(_ollama_error(response.text, model))
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event.get("error"):
                        raise RuntimeError_(_ollama_error(line, model))
                    if event.get("digest") and event.get("total"):
                        layers[event["digest"]] = (event.get("completed", 0), event["total"])
                    self._set(
                        "pulling", f"Downloading {model}" if layers else str(event.get("status", "")),
                        sum(c for c, _ in layers.values()), sum(t for _, t in layers.values()),
                    )

    async def reachable(self) -> bool:
        try:
            async with self._client(timeout=3) as client:
                return (await client.get(f"{settings.ollama_url}/api/version")).status_code == 200
        except httpx.HTTPError:
            return False

    async def installed(self) -> list[dict]:
        try:
            async with self._client(timeout=5) as client:
                response = await client.get(f"{settings.ollama_url}/api/tags")
                response.raise_for_status()
        except httpx.HTTPError:
            return []
        return [{"name": m["name"], "size": m.get("size", 0)} for m in response.json().get("models", [])]

    async def installed_names(self) -> set[str]:
        return {model["name"] for model in await self.installed()}

    async def delete_model(self, model: str) -> None:
        async with self._client(timeout=30) as client:
            response = await client.request("DELETE", f"{settings.ollama_url}/api/delete", json={"model": model})
        if response.status_code != 200:
            raise RuntimeError_(_ollama_error(response.text, model))

    async def status(self) -> dict:
        reachable = self.phase in ("ready", "pulling", "loading", "idle", "offline", "error") and await self.reachable()
        if self.phase == "ready" and not reachable:
            self._set("error", "The LLM runtime stopped. Press Retry to restart it.")
        return {
            "phase": self.phase,
            "message": self.message,
            "completed": self.completed,
            "total": self.total,
            "busy": self.busy,
            "managed": settings.llm_auto_setup,
            "available": reachable,
            "pulling_model": self.pulling_model,
            "models": await self.installed() if reachable else [],
            "loaded": await self.loaded() if reachable else [],
        }

    def shutdown(self) -> None:
        self.cancel()
        if self._alive():
            _kill_tree(self._process.pid)
            PID_FILE.unlink(missing_ok=True)


def _ollama_error(body: str, model: str) -> str:
    try:
        detail = json.loads(body).get("error", body)
    except ValueError:
        detail = body
    return f"Couldn't get {model}: {detail}"


manager = RuntimeManager()
