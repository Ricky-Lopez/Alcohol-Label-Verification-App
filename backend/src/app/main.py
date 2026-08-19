from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.config import get_settings

app = FastAPI(
    title="Alcohol Label Verification API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.include_router(health_router)


def mount_frontend(frontend_dist_dir: Path) -> None:
    if frontend_dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist_dir, html=True), name="frontend")


mount_frontend(get_settings().frontend_dist_dir)
