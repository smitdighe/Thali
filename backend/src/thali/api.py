import logging
lazy import json
lazy from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, Response
lazy from fastapi.responses import StreamingResponse

from thali.models import HealthResponse, RecommendRequest, RecommendResponse
lazy from thali.models import Trace
lazy from thali.observability import request_id_var
lazy from thali.pipeline.engine import EngineDeps, recommend, run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def server_timing(trace: Trace) -> str:
    return ", ".join(
        [
            f"parse;dur={trace.parse_ms}",
            f"fetch;dur={trace.fetch_ms}",
            f"rank;dur={trace.rank_ms}",
            f"total;dur={trace.total_ms}",
        ]
    )


def deps_of(request: Request) -> EngineDeps:
    return request.app.state.deps


@router.post("/recommend")
async def post_recommend(
    body: RecommendRequest, request: Request, response: Response
) -> RecommendResponse:
    result = await recommend(body.query, deps_of(request), request_id_var.get())
    response.headers["Server-Timing"] = server_timing(result.trace)
    return result


def frame(name: str, data: str) -> str:
    return f"event: {name}\ndata: {data}\n\n"


async def event_frames(query: str, deps: EngineDeps, request_id: str) -> AsyncIterator[str]:
    try:
        async for name, payload in run_pipeline(query, deps, request_id):
            yield frame(name, payload.model_dump_json())
    except Exception:
        logger.exception("stream pipeline failed")
        error = {"error": "internal_error", "request_id": request_id}
        body = json.dumps(error, separators=(",", ":"))
        yield frame("error", body)


@router.post("/recommend/stream")
async def post_recommend_stream(body: RecommendRequest, request: Request) -> StreamingResponse:
    request_id = request_id_var.get()
    return StreamingResponse(
        event_frames(body.query, deps_of(request), request_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
        },
    )


@router.get("/health")
async def get_health(request: Request) -> HealthResponse:
    deps = deps_of(request)
    enabled = deps.llm is not None
    return HealthResponse(
        llm_enabled=enabled,
        llm_model=deps.settings.llm_model if enabled else None,
        breakers={name: breaker.state for name, breaker in deps.breakers.items()},
    )
