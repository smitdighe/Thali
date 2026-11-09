import json

import httpx

from thali.config import Settings
from thali.evaluation import (
    CORE_PATH,
    FIELDS,
    PARAPHRASE_PATH,
    EvalCase,
    evaluate_llm,
    evaluate_rules,
    load_cases,
    render_report,
    score,
)
from thali.parsing import LlmParser
from thali.parsing.rules import parse_rules

MIN_FIELD_ACCURACY = 0.95


def test_gold_files_load():
    assert len(load_cases(CORE_PATH)) == 20
    assert len(load_cases(PARAPHRASE_PATH)) == 5
    assert len(FIELDS) == 13


def test_rules_parser_meets_core_gate():
    metrics = evaluate_rules("rules/core", load_cases(CORE_PATH))
    failures = [(f.q, f.field, f.expected, f.got) for f in metrics.failures]
    assert metrics.accuracy() >= MIN_FIELD_ACCURACY, failures
    assert metrics.invented == 0, failures


def test_paraphrase_set_is_scored_without_a_gate():
    metrics = evaluate_rules("rules/paraphrase", load_cases(PARAPHRASE_PATH))
    assert metrics.cases == 5
    assert metrics.total == 5 * len(FIELDS)
    assert metrics.invented == 0


def test_score_counts_invented_missed_and_wrong():
    cases = [
        EvalCase(q="a", intent="discovery", dish="pizza", max_price_inr=300),
        EvalCase(q="b", intent="discovery", ingredients=["egg", "fish"]),
    ]
    predictions = [
        parse_rules("burger").model_copy(update={"max_price_inr": None, "location": "Powai"}),
        parse_rules("egg"),
    ]
    metrics = score("test", cases, predictions)
    assert metrics.wrong == 2
    assert metrics.missed == 1
    assert metrics.invented == 1
    assert metrics.exact == 0
    assert metrics.per_field["intent"] == 1.0
    assert metrics.per_field["dish"] == 0.5
    assert metrics.per_field["ingredients"] == 0.5
    assert {f.field for f in metrics.failures} == {
        "dish",
        "max_price_inr",
        "location",
        "ingredients",
    }


def test_report_lists_all_rows_and_failures():
    results = {
        "rules/core": evaluate_rules("rules/core", load_cases(CORE_PATH)),
        "rules/paraphrase": evaluate_rules("rules/paraphrase", load_cases(PARAPHRASE_PATH)),
    }
    report = render_report(results)
    for row in ("rules/core", "rules/paraphrase", "llm/core", "llm/paraphrase"):
        assert f"| {row} |" in report
    assert "| llm/core | not run |" in report
    assert "### rules/paraphrase" in report


class Clock:
    def __call__(self) -> float:
        return 0.0


def answer_with_dosa(_request: httpx.Request) -> httpx.Response:
    extraction = {"intent": "discovery", "dish": {"value": "dosa", "evidence": "dosa"}}
    body = {"choices": [{"message": {"content": json.dumps(extraction)}}]}
    return httpx.Response(200, json=body)


async def test_llm_rows_are_scored_through_the_mocked_transport():
    cases = [EvalCase(q="get me dosa", intent="discovery", dish="dosa")]
    settings = Settings(_env_file=None, GROQ_API_KEY="test-key", llm_rpm=6)
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer_with_dosa)) as client:
        llm = LlmParser(client, settings, Clock())
        metrics = await evaluate_llm("llm/core", cases, llm, 0)
    assert metrics.exact == 1
    assert metrics.fallbacks == 0
