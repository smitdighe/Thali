from pathlib import Path
from typing import Literal
lazy import argparse
lazy import asyncio
lazy import sys
lazy from collections.abc import Sequence

from pydantic import BaseModel, Field
lazy import httpx

lazy from thali.config import Settings
lazy from thali.models import ParsedRequest
lazy from thali.parsing import LlmParser, parse_request, parse_rules

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"
CORE_PATH = EVAL_DIR / "core.jsonl"
PARAPHRASE_PATH = EVAL_DIR / "paraphrase.jsonl"
HINGLISH_PATH = EVAL_DIR / "hinglish.jsonl"
FIELDS = (
    "intent",
    "dish",
    "cuisine",
    "diet",
    "ingredients",
    "max_price_inr",
    "max_eta_min",
    "min_rating",
    "rating_preference",
    "price_preference",
    "speed_preference",
    "location",
    "other_preferences",
)
ROWS = ("rules/core", "rules/paraphrase", "rules/hinglish", "llm/core", "llm/paraphrase")

Verdict = Literal["correct", "invented", "missed", "wrong"]


class EvalCase(BaseModel):
    q: str
    intent: str
    dish: str | None = None
    cuisine: str | None = None
    diet: str | None = None
    ingredients: list[str] = Field(default_factory=list)
    max_price_inr: int | None = None
    max_eta_min: int | None = None
    min_rating: float | None = None
    rating_preference: str | None = None
    price_preference: str | None = None
    speed_preference: str | None = None
    location: str | None = None
    other_preferences: list[str] = Field(default_factory=list)


class Failure(BaseModel):
    q: str
    field: str
    kind: Verdict
    expected: str
    got: str


class ParserMetrics(BaseModel):
    name: str
    cases: int
    exact: int
    correct: int
    total: int
    invented: int
    missed: int
    wrong: int
    per_field: dict[str, float]
    failures: list[Failure]
    fallbacks: int = 0

    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def exact_rate(self) -> float:
        return self.exact / self.cases if self.cases else 0.0


def load_cases(path: Path) -> list[EvalCase]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [EvalCase.model_validate_json(line) for line in lines if line.strip()]


def field_value(source: BaseModel, field: str) -> object:
    value = getattr(source, field)
    return frozenset(value) if isinstance(value, list) else value


def show(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, frozenset):
        return "[" + ", ".join(sorted(value)) + "]"
    return str(value)


def is_unset(value: object) -> bool:
    return value is None or value == frozenset()


def judge(expected: object, got: object) -> Verdict:
    if expected == got:
        return "correct"
    if is_unset(expected):
        return "invented"
    if is_unset(got):
        return "missed"
    return "wrong"


def score(
    name: str, cases: Sequence[EvalCase], predictions: Sequence[ParsedRequest], fallbacks: int = 0
) -> ParserMetrics:
    tally = {"correct": 0, "invented": 0, "missed": 0, "wrong": 0}
    per_field = dict.fromkeys(FIELDS, 0)
    failures: list[Failure] = []
    exact = 0
    for case, prediction in zip(cases, predictions, strict=True):
        verdicts: list[Verdict] = []
        for field in FIELDS:
            expected, got = field_value(case, field), field_value(prediction, field)
            verdict = judge(expected, got)
            verdicts.append(verdict)
            tally[verdict] += 1
            per_field[field] += verdict == "correct"
            if verdict != "correct":
                failures.append(
                    Failure(
                        q=case.q, field=field, kind=verdict, expected=show(expected), got=show(got)
                    )
                )
        exact += all(verdict == "correct" for verdict in verdicts)
    return ParserMetrics(
        name=name,
        cases=len(cases),
        exact=exact,
        correct=tally["correct"],
        total=len(cases) * len(FIELDS),
        invented=tally["invented"],
        missed=tally["missed"],
        wrong=tally["wrong"],
        per_field={field: hits / len(cases) if cases else 0.0 for field, hits in per_field.items()},
        failures=failures,
        fallbacks=fallbacks,
    )


def evaluate_rules(name: str, cases: Sequence[EvalCase]) -> ParserMetrics:
    return score(name, cases, [parse_rules(case.q) for case in cases])


async def evaluate_llm(
    name: str, cases: Sequence[EvalCase], llm: LlmParser, delay_s: float
) -> ParserMetrics:
    predictions: list[ParsedRequest] = []
    fallbacks = 0
    for index, case in enumerate(cases):
        if index and delay_s:
            await asyncio.sleep(delay_s)
        parsed, reason = await parse_request(case.q, llm)
        fallbacks += reason is not None
        predictions.append(parsed)
    return score(name, cases, predictions, fallbacks)


def render_report(results: dict[str, ParserMetrics]) -> str:
    lines = [
        "# Parser evaluation",
        "",
        "| parser/set | cases | field accuracy | exact match | invented | missed | wrong |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in ROWS:
        metrics = results.get(row)
        if metrics is None:
            lines.append(f"| {row} | not run | | | | | |")
            continue
        exact = f"{metrics.exact_rate():.3f} ({metrics.exact}/{metrics.cases})"
        lines.append(
            f"| {row} | {metrics.cases} | {metrics.accuracy():.3f} | {exact} | "
            f"{metrics.invented} | {metrics.missed} | {metrics.wrong} |"
        )
    lines += ["", "## Per-field accuracy", "", "| field | " + " | ".join(ROWS) + " |"]
    lines.append("|---|" + "---|" * len(ROWS))
    for field in FIELDS:
        cells = [f"{results[row].per_field[field]:.2f}" if row in results else "" for row in ROWS]
        lines.append(f"| {field} | " + " | ".join(cells) + " |")
    lines += ["", "## Failures"]
    for row in ROWS:
        if row not in results:
            continue
        metrics = results[row]
        lines += ["", f"### {row}", ""]
        if metrics.fallbacks:
            lines += [f"LLM unavailable for {metrics.fallbacks} requests; rules answered.", ""]
        if not metrics.failures:
            lines.append("none")
        for failure in metrics.failures:
            lines.append(
                f"- `{failure.q}` — {failure.field} ({failure.kind}): "
                f"expected {failure.expected}, got {failure.got}"
            )
    return "\n".join(lines) + "\n"


async def run_llm_rows(settings: Settings) -> dict[str, ParserMetrics]:
    delay_s = 60 / settings.llm_rpm
    results: dict[str, ParserMetrics] = {}
    async with httpx.AsyncClient() as client:
        llm = LlmParser(client, settings)
        for label, path in (("core", CORE_PATH), ("paraphrase", PARAPHRASE_PATH)):
            name = f"llm/{label}"
            results[name] = await evaluate_llm(name, load_cases(path), llm, delay_s)
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="thali.evaluation")
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--write", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    results = {
        "rules/core": evaluate_rules("rules/core", load_cases(CORE_PATH)),
        "rules/paraphrase": evaluate_rules("rules/paraphrase", load_cases(PARAPHRASE_PATH)),
        "rules/hinglish": evaluate_rules("rules/hinglish", load_cases(HINGLISH_PATH)),
    }
    if args.llm:
        settings = Settings()
        if not settings.groq_api_key:
            print("GROQ_API_KEY is not set", file=sys.stderr)
            return 2
        results |= asyncio.run(run_llm_rows(settings))
    report = render_report(results)
    if args.write is not None:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
