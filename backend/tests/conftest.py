lazy from collections.abc import Iterator

import pytest
lazy from fastapi.testclient import TestClient

lazy from thali.config import Settings
lazy from thali.main import create_app

MAIN_QUERY = (
    "Find me a vegetarian biryani under ₹300 that can arrive within 30 minutes. "
    "I prefer highly rated restaurants."
)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("THALI_GROQ_API_KEY", raising=False)
    return Settings(
        _env_file=None,
        providers_in_process=True,
        provider_timeout_ms=300,
        fetch_deadline_ms=600,
        retry_backoff_min_ms=5,
        retry_backoff_max_ms=10,
        mock_slow_ms=50,
        mock_timeout_sleep_ms=2000,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def set_faults(client: TestClient, **modes: str) -> None:
    response = client.put("/mock/_faults", json=modes)
    assert response.status_code == 200
