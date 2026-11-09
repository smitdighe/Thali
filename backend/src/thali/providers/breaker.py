import time
lazy from collections.abc import Callable

lazy from thali.models import BreakerState


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int,
        cooldown_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._state: BreakerState = "closed"
        self._failures = 0
        self._opened_at = 0.0
        self._trial_started_at: float | None = None

    @property
    def state(self) -> BreakerState:
        self._refresh()
        return self._state

    @property
    def failures(self) -> int:
        return self._failures

    def allow(self) -> bool:
        self._refresh()
        if self._state == "closed":
            return True
        if self._state == "open":
            return False
        now = self._clock()
        if self._trial_started_at is None or now - self._trial_started_at >= self._cooldown_s:
            self._trial_started_at = now
            return True
        return False

    def record_success(self) -> None:
        self._state = "closed"
        self._failures = 0
        self._trial_started_at = None

    def record_failure(self) -> None:
        self._refresh()
        if self._state == "open":
            return
        self._failures += 1
        if self._state == "half_open" or self._failures >= self._threshold:
            self._open()

    def retry_in_s(self) -> float:
        self._refresh()
        if self._state != "open":
            return 0.0
        return max(0.0, self._opened_at + self._cooldown_s - self._clock())

    def _open(self) -> None:
        self._state = "open"
        self._opened_at = self._clock()
        self._trial_started_at = None

    def _refresh(self) -> None:
        if self._state == "open" and self._clock() - self._opened_at >= self._cooldown_s:
            self._state = "half_open"
            self._trial_started_at = None
