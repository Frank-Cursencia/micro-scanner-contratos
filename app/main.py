from fastapi import FastAPI

from app.api.routes_extract import router as extract_router
from app.api.routes_health import router as health_router
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.service_name,
        version=settings.service_version,
        description="Escáner de PDF a JSON dinámico para el formulario de contratos de ventas.",
    )
    app.include_router(health_router)
    app.include_router(extract_router)
    return app


app = create_app()
