import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
lazy import httpx
lazy from fastapi.responses import JSONResponse

from thali import api
from thali.config import Settings, get_settings
from thali.mock.app import create_mock_app
from thali.observability import RequestContextMiddleware, configure_logging, request_id_var
lazy from thali.parsing import LlmParser
lazy from thali.pipeline.engine import EngineDeps
lazy from thali.providers.bitebox import BiteboxAdapter
lazy from thali.providers.breaker import CircuitBreaker
lazy from thali.providers.khaana import KhaanaAdapter
lazy from thali.providers.tiffinly import TiffinlyAdapter

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
IN_PROCESS_BASE_URL = "http://mock"


def provider_client_for(settings: Settings, mock_app: FastAPI) -> httpx.AsyncClient:
    if settings.providers_in_process:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app), base_url=IN_PROCESS_BASE_URL
        )
    return httpx.AsyncClient(base_url=settings.provider_base_url)


def llm_client_for(
    settings: Settings, transport: httpx.AsyncBaseTransport | None
) -> httpx.AsyncClient | None:
    if not settings.groq_api_key:
        return None
    return httpx.AsyncClient(
        base_url=settings.llm_base_url,
        transport=transport,
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
    )


def static_directory(settings: Settings) -> Path | None:
    candidate = (
        Path(settings.static_dir) if settings.static_dir else REPO_ROOT / "frontend" / "dist"
    )
    return candidate if candidate.is_dir() else None


def create_app(
    settings: Settings | None = None,
    llm_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    mock_app = create_mock_app(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        provider_client = provider_client_for(settings, mock_app)
        llm_client = llm_client_for(settings, llm_transport)
        adapters = [BiteboxAdapter(), TiffinlyAdapter(), KhaanaAdapter()]
        app.state.deps = EngineDeps(
            settings=settings,
            provider_client=provider_client,
            adapters=adapters,
            breakers={
                adapter.name: CircuitBreaker(settings.breaker_failures, settings.breaker_cooldown_s)
                for adapter in adapters
            },
            llm=LlmParser(llm_client, settings) if llm_client is not None else None,
        )
        try:
            yield
        finally:
            await provider_client.aclose()
            if llm_client is not None:
                await llm_client.aclose()

    app = FastAPI(title="Thali", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Server-Timing"],
    )
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, error: Exception) -> JSONResponse:
        request_id = request_id_var.get()
        logger.error("unhandled error", exc_info=error)
        return JSONResponse(
            {"error": "internal_error", "request_id": request_id},
            status_code=500,
            headers={"X-Request-ID": request_id},
        )

    app.mount("/mock", mock_app)
    app.include_router(api.router)
    directory = static_directory(settings)
    if directory is not None:
        app.mount("/", StaticFiles(directory=directory, html=True), name="frontend")
    return app


app = create_app()
