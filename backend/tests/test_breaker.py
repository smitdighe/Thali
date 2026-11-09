from thali.providers.breaker import CircuitBreaker


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_breaker(clock: FakeClock) -> CircuitBreaker:
    return CircuitBreaker(failure_threshold=3, cooldown_s=30.0, clock=clock)


def test_starts_closed_and_allows():
    breaker = make_breaker(FakeClock())
    assert breaker.state == "closed"
    assert breaker.allow()
    assert breaker.retry_in_s() == 0.0


def test_opens_at_threshold():
    breaker = make_breaker(FakeClock())
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == "closed"
    assert breaker.allow()
    breaker.record_failure()
    assert breaker.state == "open"
    assert not breaker.allow()
    assert breaker.failures == 3


def test_success_resets_consecutive_count():
    breaker = make_breaker(FakeClock())
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == "closed"


def test_retry_in_counts_down():
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        breaker.record_failure()
    assert breaker.retry_in_s() == 30.0
    clock.advance(12)
    assert breaker.retry_in_s() == 18.0


def test_half_open_after_cooldown_allows_single_trial():
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        breaker.record_failure()
    clock.advance(29.9)
    assert breaker.state == "open"
    assert not breaker.allow()
    clock.advance(0.2)
    assert breaker.state == "half_open"
    assert breaker.allow()
    assert not breaker.allow()
    assert not breaker.allow()


def test_trial_success_closes_and_resets():
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        breaker.record_failure()
    clock.advance(31)
    assert breaker.allow()
    breaker.record_success()
    assert breaker.state == "closed"
    assert breaker.failures == 0
    assert breaker.allow()
    assert breaker.allow()


def test_trial_failure_reopens_for_a_full_cooldown():
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        breaker.record_failure()
    clock.advance(31)
    assert breaker.allow()
    breaker.record_failure()
    assert breaker.state == "open"
    assert not breaker.allow()
    assert breaker.retry_in_s() == 30.0
    clock.advance(31)
    assert breaker.allow()


def test_abandoned_trial_is_retried_after_another_cooldown():
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        breaker.record_failure()
    clock.advance(31)
    assert breaker.allow()
    assert not breaker.allow()
    clock.advance(31)
    assert breaker.allow()
