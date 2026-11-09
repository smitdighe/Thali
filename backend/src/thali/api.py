import logging
lazy import json
lazy from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, Response
lazy from fastapi.responses import JSONResponse, StreamingResponse

from thali.models import (
    HealthResponse,
    MetricsResponse,
    RecommendRequest,
    RecommendResponse,
    RefineRequest,
)
lazy from thali.models import ParsedRequest, Trace
lazy from thali.observability import request_id_var
lazy from thali.parsing import parse_request
lazy from thali.parsing.rules import has_content
lazy from thali.pipeline.engine import EngineDeps, PipelineContext, recommend, run_pipeline
lazy from thali.pipeline.refine import (
    ACTION_LABELS,
    FIELDS,
    apply_action,
    apply_drop,
    drop_label,
    is_set,
    merge_text,
)
lazy from thali.sessions import SessionEntry

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


def error_response(status: int, code: str) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status)


def unchanged_response(
    text: str, entry: SessionEntry, request_id: str, deps: EngineDeps
) -> RecommendResponse:
    parsed = entry.parsed
    carried = [name for name in FIELDS if is_set(parsed, name)]
    kept = parsed.model_copy(
        update={"refined_from": request_id, "carried_over": carried, "adjusted": []}
    )
    current_id = request_id_var.get()
    deps.sessions.put(current_id, kept, entry.pick)
    return RecommendResponse(
        request_id=current_id,
        query=text,
        parsed=kept,
        clarification=f"I couldn't find a change in “{text}”.",
    )


async def refined_request(
    body: RefineRequest, entry: SessionEntry, deps: EngineDeps
) -> tuple[ParsedRequest | None, str]:
    if body.text is not None:
        followup, _fallback = await parse_request(body.text, deps.llm)
        if not has_content(followup):
            return None, body.text
        return merge_text(entry.parsed, followup, body.request_id), body.text
    if body.action is not None and entry.pick is not None:
        merged = apply_action(entry.parsed, entry.pick, body.action, body.request_id)
        return merged, ACTION_LABELS[body.action]
    name = body.drop or ""
    return apply_drop(entry.parsed, name, body.request_id), drop_label(name)


@router.post("/refine", response_model=RecommendResponse)
async def post_refine(
    body: RefineRequest, request: Request, response: Response
) -> RecommendResponse | JSONResponse:
    deps = deps_of(request)
    entry = deps.sessions.get(body.request_id)
    if entry is None:
        return error_response(404, "unknown_or_expired_request")
    if body.action is not None and entry.pick is None:
        return error_response(409, "no_pick_to_refine")
    if body.drop is not None and body.drop not in FIELDS:
        return error_response(422, "unknown_field")
    merged, label = await refined_request(body, entry, deps)
    if merged is None:
        return unchanged_response(label, entry, body.request_id, deps)
    result = await recommend(label, deps, request_id_var.get(), PipelineContext(parsed=merged))
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


@router.get("/metrics")
async def get_metrics(request: Request) -> MetricsResponse:
    deps = deps_of(request)
    return deps.metrics.snapshot(deps.breakers)
