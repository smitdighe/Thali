from pathlib import Path
lazy import argparse
lazy import asyncio
lazy import json
lazy import sys
lazy from collections.abc import Sequence

from pydantic import BaseModel, Field
lazy import httpx

lazy from thali.config import get_settings
lazy from thali.main import create_app
lazy from thali.models import ParsedRequest, RecommendResponse

MAIN_QUERY = (
    "Find me a vegetarian biryani under ₹300 that can arrive within 30 minutes. "
    "I prefer highly rated restaurants."
)
DEFAULT_OUT = Path(__file__).resolve().parents[3] / "docs"
BASE_URL = "http://thali"
NOT_SPECIFIED = "not specified"
PARSED_FIELDS = (
    "intent",
    "dish",
    "cuisine",
    "ingredients",
    "diet",
    "max_price_inr",
    "max_eta_min",
    "min_rating",
    "rating_preference",
    "price_preference",
    "speed_preference",
    "location",
    "other_preferences",
    "parser",
)


class Sample(BaseModel):
    name: str
    query: str
    faults: dict[str, str] = Field(default_factory=dict)


SAMPLES = (
    Sample(name="01-normal", query=MAIN_QUERY),
    Sample(name="02-missing-info", query="suggest a biryani"),
    Sample(name="03-provider-timeout", query=MAIN_QUERY, faults={"tiffinly": "timeout"}),
    Sample(name="04-incomplete-data", query=MAIN_QUERY, faults={"bitebox": "partial"}),
    Sample(name="05-preferences", query="Jain thali in Dadar under ₹300"),
    Sample(name="06-cheap-and-fast", query="cheap veg momos in Powai asap"),
    Sample(name="07-clarification", query="within 45"),
)


async def run_sample(sample: Sample) -> RecommendResponse:
    app = create_app(get_settings().model_copy(update={"providers_in_process": True}))
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client,
    ):
        if sample.faults:
            await client.put("/mock/_faults", json=sample.faults)
        response = await client.post(
            "/api/v1/recommend",
            json={"query": sample.query},
            headers={"X-Request-ID": sample.name},
            timeout=30,
        )
        response.raise_for_status()
        return RecommendResponse.model_validate(response.json())


def cell(value: object) -> str:
    if value is None or value == []:
        return NOT_SPECIFIED
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def parsed_table(parsed: ParsedRequest) -> list[str]:
    rows = ["| Field | Value |", "| --- | --- |"]
    rows.extend(f"| {name} | {cell(getattr(parsed, name))} |" for name in PARSED_FIELDS)
    return rows


def faults_text(faults: dict[str, str]) -> str:
    if not faults:
        return "none"
    return ", ".join(f"{name}={mode}" for name, mode in faults.items())


def bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["none"]


def render_sample(sample: Sample, response: RecommendResponse) -> str:
    lines = [
        f"## {sample.name}",
        "",
        f"Query: `{sample.query}`",
        "",
        f"Faults: {faults_text(sample.faults)}",
        "",
        *parsed_table(response.parsed),
        "",
    ]
    recommendation = response.recommendation
    if recommendation is not None:
        listing = recommendation.option.best.listing
        lines += [
            f"Pick: {listing.item} at {listing.restaurant} via {listing.provider_label}",
            "",
            f"Summary: {recommendation.summary}",
            "",
            "Reasons:",
            "",
            *bullets(recommendation.reasons),
            "",
        ]
    else:
        lines += [f"Clarification: {cell(response.clarification)}", ""]
    lines += ["Warnings:", "", *bullets(response.warnings), ""]
    return "\n".join(lines)


def render_index(rendered: list[str]) -> str:
    return "\n".join(["# Sample responses", "", *rendered])


def write_sample(out_dir: Path, sample: Sample, response: RecommendResponse) -> None:
    path = out_dir / "samples" / f"{sample.name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(response.model_dump(mode="json"), indent=2, ensure_ascii=False)
    path.write_text(body + "\n", encoding="utf-8")


async def run_all(out_dir: Path) -> None:
    rendered: list[str] = []
    for sample in SAMPLES:
        response = await run_sample(sample)
        write_sample(out_dir, sample, response)
        rendered.append(render_sample(sample, response))
        print(f"wrote {sample.name}")
    (out_dir / "samples.md").write_text(render_index(rendered), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="thali.samples")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(run_all(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
