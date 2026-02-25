"""FastAPI worker server — the background HTTP service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from cursor_mem.config import Config, setup_logging
from cursor_mem.storage.database import init_db
from cursor_mem.worker.routes import router
from cursor_mem.worker.session_manager import SessionManager

logger = logging.getLogger("cursor_mem")


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or Config.load()
    setup_logging(cfg.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = init_db()
        app.state.db_conn = conn
        app.state.config = cfg
        app.state.session_manager = SessionManager(conn, cfg)
        logger.info("cursor-mem worker started on %s:%d", cfg.host, cfg.port)
        yield
        conn.close()
        logger.info("Database connection closed")

    app = FastAPI(title="cursor-mem", version="0.1.0", docs_url="/api/docs", lifespan=lifespan)
    app.include_router(router)

    viewer_path = Path(__file__).parent.parent / "ui" / "viewer.html"

    @app.get("/")
    async def viewer():
        if viewer_path.exists():
            return FileResponse(viewer_path, media_type="text/html")
        return {"message": "cursor-mem worker is running. Web viewer not found."}

    return app


def run_server(config: Config | None = None) -> None:
    """Start the uvicorn server (blocking call)."""
    import uvicorn

    cfg = config or Config.load()
    app = create_app(cfg)
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="warning")


if __name__ == "__main__":
    run_server()
