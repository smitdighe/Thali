from fastapi import APIRouter, Request, Response

from thali.models import HealthResponse, RecommendRequest, RecommendResponse
lazy from thali.models import Trace
lazy from thali.observability import request_id_var
lazy from thali.pipeline.engine import EngineDeps, recommend

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


@router.get("/health")
async def get_health(request: Request) -> HealthResponse:
    deps = deps_of(request)
    enabled = deps.llm is not None
    return HealthResponse(
        llm_enabled=enabled,
        llm_model=deps.settings.llm_model if enabled else None,
        breakers={name: breaker.state for name, breaker in deps.breakers.items()},
    )
