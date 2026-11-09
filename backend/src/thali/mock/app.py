from typing import Literal
lazy import asyncio
lazy import csv
lazy import io
lazy import json
lazy from collections.abc import Callable
lazy from pathlib import Path
lazy from typing import Any

from pydantic import BaseModel
lazy from fastapi import FastAPI
lazy from fastapi.responses import JSONResponse, Response

lazy from thali.config import Settings
lazy from thali.models import FaultMode

ProviderName = Literal["bitebox", "tiffinly", "khaana"]
PROVIDERS: tuple[ProviderName, ...] = ("bitebox", "tiffinly", "khaana")
CSV_MEDIA_TYPE = "text/csv; charset=utf-8"
MALFORMED_JSON_LENGTH = 120
MALFORMED_CSV_BODY = "<html><body>Service temporarily unavailable</body></html>"


class TiffinlyQuery(BaseModel):
    query: str = ""


def load_json(name: str) -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "data" / name
    return json.loads(path.read_text(encoding="utf-8"))


def load_text(name: str) -> str:
    path = Path(__file__).resolve().parent / "data" / name
    return path.read_bytes().decode("utf-8")


def mock_headers(mode: str) -> dict[str, str]:
    return {"X-Mock-Mode": mode}


def error_response(mode: str) -> JSONResponse:
    return JSONResponse(
        {"error": "upstream unavailable"}, status_code=503, headers=mock_headers(mode)
    )


async def apply_delay(mode: str, settings: Settings) -> None:
    if mode == "slow":
        await asyncio.sleep(settings.mock_slow_ms / 1000)
    elif mode == "timeout":
        await asyncio.sleep(settings.mock_timeout_sleep_ms / 1000)


def json_response(
    mode: str, payload: dict[str, Any], strip: Callable[[dict[str, Any]], dict[str, Any]]
) -> Response:
    if mode == "error":
        return error_response(mode)
    if mode == "partial":
        payload = strip(payload)
    if mode == "malformed":
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return Response(
            body[:MALFORMED_JSON_LENGTH], media_type="application/json", headers=mock_headers(mode)
        )
    return JSONResponse(payload, headers=mock_headers(mode))


def csv_response(mode: str, text: str) -> Response:
    if mode == "error":
        return error_response(mode)
    if mode == "malformed":
        text = MALFORMED_CSV_BODY
    elif mode == "partial":
        text = blank_rating_columns(text)
    return Response(text, media_type=CSV_MEDIA_TYPE, headers=mock_headers(mode))


def strip_bitebox(payload: dict[str, Any]) -> dict[str, Any]:
    dropped = {"rating", "ratings_count", "eta_minutes"}
    results = [{k: v for k, v in r.items() if k not in dropped} for r in payload["results"]]
    return {**payload, "results": results}


def strip_tiffinly(payload: dict[str, Any]) -> dict[str, Any]:
    dropped = {"score", "votes", "deliveryTime"}
    outlets = [{k: v for k, v in o.items() if k not in dropped} for o in payload["data"]["outlets"]]
    return {**payload, "data": {**payload["data"], "outlets": outlets}}


def blank_rating_columns(text: str) -> str:
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    blanked = {header.index("avg_rating"), header.index("num_ratings")}
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    for row in rows[1:]:
        writer.writerow("" if i in blanked else value for i, value in enumerate(row))
    return out.getvalue()


def bitebox_matches(result: dict[str, Any], q: str, area: str | None) -> bool:
    needle = q.lower()
    in_dish = needle in result["dish"].lower()
    in_cuisine = any(needle in cuisine.lower() for cuisine in result["cuisine"])
    if not (in_dish or in_cuisine):
        return False
    return not area or result["restaurant"]["area"] == area


def filter_tiffinly(payload: dict[str, Any], query: str) -> dict[str, Any]:
    needle = query.lower()
    outlets = []
    for outlet in payload["data"]["outlets"]:
        menu = [item for item in outlet["menu"] if needle in item["title"].lower()]
        if menu:
            outlets.append({**outlet, "menu": menu})
    return {**payload, "data": {**payload["data"], "outlets": outlets}}


def create_mock_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Thali mock providers")
    app.state.faults = dict.fromkeys(PROVIDERS, "ok")
    bitebox = load_json("bitebox.json")
    tiffinly = load_json("tiffinly.json")
    khaana = load_text("khaana.csv")

    @app.get("/bitebox/v2/search")
    async def bitebox_search(q: str = "", area: str | None = None) -> Response:
        mode = app.state.faults["bitebox"]
        await apply_delay(mode, settings)
        results = [r for r in bitebox["results"] if bitebox_matches(r, q, area)]
        payload = {"api_version": bitebox["api_version"], "results": results}
        return json_response(mode, payload, strip_bitebox)

    @app.post("/tiffinly/api/v3/outlets/search")
    async def tiffinly_search(body: TiffinlyQuery) -> Response:
        mode = app.state.faults["tiffinly"]
        await apply_delay(mode, settings)
        return json_response(mode, filter_tiffinly(tiffinly, body.query), strip_tiffinly)

    @app.get("/khaana/v1/listings.csv")
    async def khaana_listings() -> Response:
        mode = app.state.faults["khaana"]
        await apply_delay(mode, settings)
        return csv_response(mode, khaana)

    if settings.enable_fault_api:

        @app.get("/_faults")
        async def get_faults() -> dict[str, str]:
            return app.state.faults

        @app.put("/_faults")
        async def put_faults(updates: dict[ProviderName, FaultMode]) -> dict[str, str]:
            app.state.faults.update(updates)
            return app.state.faults

        @app.post("/_faults/reset")
        async def reset_faults() -> dict[str, str]:
            app.state.faults.update(dict.fromkeys(PROVIDERS, "ok"))
            return app.state.faults

    return app
