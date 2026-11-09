lazy from thali.models import ParsedRequest
lazy from thali.parsing.grounding import ground
lazy from thali.parsing.llm import LlmParser, LlmUnavailable
lazy from thali.parsing.rules import finalize, parse_rules

__all__ = ["LlmParser", "LlmUnavailable", "parse_request", "parse_rules"]


async def parse_request(query: str, llm: LlmParser | None) -> tuple[ParsedRequest, str | None]:
    rules = parse_rules(query)
    if llm is None:
        return rules, None
    cached = llm.cached(query)
    if cached is not None:
        return cached, None
    try:
        extraction = await llm.extract(query)
    except LlmUnavailable as error:
        return rules, error.reason
    grounded = finalize(ground(query, extraction, rules))
    llm.remember(query, grounded)
    return grounded, None
