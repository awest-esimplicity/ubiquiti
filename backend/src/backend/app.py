"""FastAPI application exposing UniFi device control endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .router import router as api_router
from .ubiquiti.utils import configure_logging, logger

configure_logging()

app = FastAPI(
    title="UniFi Device Control API",
    version="1.0.0",
    description=(
        "HTTP API that mirrors the device management capabilities of the "
        "Streamlit dashboard."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Simple readiness probe."""
    return {"status": "ok"}


def _find_project_root() -> Path:
    """Locate the repository root by searching for the frontend directory."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "frontend").exists():
            return parent
    return Path(__file__).resolve().parents[2]


def _mount_frontend_assets() -> None:
    """Serve the built frontend if the dist directory is available."""
    project_root = _find_project_root()
    dist_dir = project_root / "frontend" / "dist"
    if not dist_dir.exists():
        logger.bind(dist_path=str(dist_dir)).debug(
            "Frontend build directory not found; skipping static mount"
        )
        return

    logger.bind(dist_path=str(dist_dir)).info("Mounting frontend static assets")
    app.mount(
        "/",
        StaticFiles(directory=str(dist_dir), html=True),
        name="frontend",
    )


_mount_frontend_assets()
