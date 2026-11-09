from dataclasses import dataclass
lazy import math
lazy from collections import deque

lazy from thali.models import MetricsResponse, ParserMetrics, ProviderMetrics, ProviderReport
lazy from thali.providers.breaker import CircuitBreaker

BUFFER_SIZE = 500
RECENT_COUNT = 30


@dataclass(frozen=True)
class RequestSample:
    total_ms: float
    parser: str
    fallback: bool


@dataclass(frozen=True)
class CallSample:
    latency_ms: float
    status: str


def nearest_rank(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(percent * len(ordered) / 100))
    return float(ordered[rank - 1])


class Metrics:
    def __init__(self, buffer_size: int = BUFFER_SIZE) -> None:
        self.buffer_size = buffer_size
        self.requests_total = 0
        self.requests: deque[RequestSample] = deque(maxlen=buffer_size)
        self.calls_total: dict[str, int] = {}
        self.calls: dict[str, deque[CallSample]] = {}

    def record_request(self, total_ms: float, parser: str, fallback: bool) -> None:
        self.requests_total += 1
        self.requests.append(RequestSample(total_ms, parser, fallback))

    def record_call(self, report: ProviderReport) -> None:
        self.calls_total[report.name] = self.calls_total.get(report.name, 0) + 1
        buffer = self.calls.setdefault(report.name, deque(maxlen=self.buffer_size))
        buffer.append(CallSample(report.latency_ms, report.status))

    def parser_metrics(self) -> ParserMetrics:
        return ParserMetrics(
            rules=sum(1 for sample in self.requests if sample.parser == "rules"),
            llm=sum(1 for sample in self.requests if sample.parser == "llm"),
            fallbacks=sum(1 for sample in self.requests if sample.fallback),
        )

    def provider_metrics(self, name: str, breaker: CircuitBreaker) -> ProviderMetrics:
        samples = self.calls.get(name, deque())
        latencies = [sample.latency_ms for sample in samples]
        ok = sum(1 for sample in samples if sample.status == "ok")
        failed = ("error", "malformed")
        return ProviderMetrics(
            calls=self.calls_total.get(name, 0),
            ok_rate=round(ok / len(samples), 4) if samples else 0.0,
            p50_ms=nearest_rank(latencies, 50),
            p95_ms=nearest_rank(latencies, 95),
            timeouts=sum(1 for sample in samples if sample.status == "timeout"),
            errors=sum(1 for sample in samples if sample.status in failed),
            circuit_open=sum(1 for sample in samples if sample.status == "circuit_open"),
            breaker=breaker.state,
        )

    def snapshot(self, breakers: dict[str, CircuitBreaker]) -> MetricsResponse:
        totals = [sample.total_ms for sample in self.requests]
        return MetricsResponse(
            requests=self.requests_total,
            p50_ms=nearest_rank(totals, 50),
            p95_ms=nearest_rank(totals, 95),
            recent_total_ms=totals[-RECENT_COUNT:],
            parser=self.parser_metrics(),
            providers={
                name: self.provider_metrics(name, breaker) for name, breaker in breakers.items()
            },
        )
