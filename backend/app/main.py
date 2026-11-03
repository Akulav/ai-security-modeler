"""FastAPI entry point. Serves the API and, once built, the frontend."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import PROJECT_ROOT
from .database import init_db
from .routers import analysis, graph, hibp, launcher, llm
from .services.runtime import manager

FRONTEND_DIST: Path = PROJECT_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    manager.idle_seconds = llm.stored_idle_seconds()
    manager.start(llm.selected_model)
    yield
    manager.shutdown()


app = FastAPI(title="Personal Security & Infrastructure Modeler", lifespan=lifespan)

# The API has no login because it only listens on loopback. These two stop other websites
# open in your browser from reading it (CORS) or reaching it via DNS rebinding (hosts).
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(graph.router)
app.include_router(hibp.router)
app.include_router(analysis.router)
app.include_router(llm.router)
app.include_router(launcher.router)

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404)
        # Top-level files from the build, such as the icon. Anything else is a page of the app.
        wanted = (FRONTEND_DIST / path).resolve()
        if path and wanted.parent == FRONTEND_DIST.resolve() and wanted.is_file():
            return FileResponse(wanted)
        return FileResponse(FRONTEND_DIST / "index.html")
