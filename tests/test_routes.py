"""End-to-end route tests via TestClient — registry fetches mocked."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import RegistrySkill
from app.registry_client import RegistryCache, RegistryFetchError

_ESCROW = RegistrySkill(
    id="1",
    name="AgentCourt Escrow",
    description="Secure agent escrow and dispute resolution",
    tags=("escrow",),
)


class _StubCache(RegistryCache):
    """Cache double returning canned data without any network."""

    def __init__(self, skills: list[RegistrySkill], skipped: int = 0) -> None:
        super().__init__("https://registry.example", ttl_seconds=300)
        self._stub_skills = skills
        self._skipped = skipped

    def get(self) -> list[RegistrySkill]:
        return list(self._stub_skills)


class _FailingCache(RegistryCache):
    """Cache double simulating an unreachable registry."""

    def __init__(self) -> None:
        super().__init__("https://registry.example", ttl_seconds=300)

    def get(self) -> list[RegistrySkill]:
        raise RegistryFetchError("registry unreachable (stub)")


def _client(cache: RegistryCache) -> TestClient:
    app.state.registry_cache = cache
    return TestClient(app)


class TestCheckRoute:
    def test_near_duplicate_proposal_is_flagged(self) -> None:
        client = _client(_StubCache([_ESCROW]))
        response = client.post(
            "/check",
            json={
                "name": "Agent Escrow Court",
                "description": "Escrow and dispute resolution for secure agent payments",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["is_likely_duplicate"] is True
        assert body["duplicates"][0]["id"] == "1"
        assert body["registry_count"] == 1

    def test_unrelated_proposal_returns_no_duplicates(self) -> None:
        client = _client(_StubCache([_ESCROW]))
        response = client.post(
            "/check",
            json={"name": "Recipe Recommender", "description": "Suggests dinner recipes"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["duplicates"] == []
        assert body["is_likely_duplicate"] is False

    def test_empty_registry_returns_explicit_zero_count(self) -> None:
        client = _client(_StubCache([]))
        response = client.post("/check", json={"name": "X", "description": "anything"})
        assert response.status_code == 200
        assert response.json() == {
            "duplicates": [],
            "is_likely_duplicate": False,
            "registry_count": 0,
        }

    def test_unreachable_registry_returns_503_not_empty_green(self) -> None:
        client = _client(_FailingCache())
        response = client.post("/check", json={"name": "X", "description": "anything"})
        assert response.status_code == 503

    def test_blank_name_returns_422(self) -> None:
        client = _client(_StubCache([_ESCROW]))
        response = client.post("/check", json={"name": "", "description": "anything"})
        assert response.status_code == 422

    def test_missing_description_returns_422(self) -> None:
        client = _client(_StubCache([_ESCROW]))
        response = client.post("/check", json={"name": "X"})
        assert response.status_code == 422


class TestInspectionEndpoints:
    def test_get_skill_md_returns_markdown_content_type(self) -> None:
        client = _client(_StubCache([_ESCROW]))
        response = client.get("/skill.md")
        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]

    def test_get_health_reports_registry_state(self) -> None:
        client = _client(_StubCache([_ESCROW]))
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert "1 skills cached" in body["registry"]

    def test_get_health_degraded_when_registry_unreachable(self) -> None:
        client = _client(_FailingCache())
        body = client.get("/health").json()
        assert body["status"] == "degraded"
        assert "unreachable" in body["registry"]


@pytest.fixture(autouse=True)
def _restore_cache() -> object:  # pyright: ignore[reportUnusedFunction] — autouse fixture, invoked by pytest
    """Restore the real cache after each test so tests never leak state."""
    original = app.state.registry_cache
    yield
    app.state.registry_cache = original
