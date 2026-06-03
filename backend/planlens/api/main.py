from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import Settings
from ..db import init_db
from .routes_dashboard import router as dashboard_router
from .routes_hearings import router as hearings_router
from .routes_search import router as search_router


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()
    init_db(app_settings.db_path)

    app = FastAPI(
        title="SF Public Record API",
        description="AI-assisted accountability for San Francisco planning records.",
        version="0.1.0",
    )
    app.state.settings = app_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(hearings_router)
    app.include_router(dashboard_router)
    app.include_router(search_router)
    return app


app = create_app()
