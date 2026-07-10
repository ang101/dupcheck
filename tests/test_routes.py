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
    """Cache double returning canned data without any network.

    ``version`` is ``id(self)`` — unique per instance — so a fresh
    ``_StubCache`` in one test can never cause the similarity index cached
    from a *different* stub instance in an earlier test to be silently
    reused against different skill data (the base class's real ``version``
    only changes on an actual network refetch, which this double's
    overridden ``get()`` never triggers).
    """

    def __init__(self, skills: list[RegistrySkill], skipped: int = 0) -> None:
        super().__init__("https://registry.example", ttl_seconds=300)
        self._stub_skills = skills
        self._skipped = skipped

    def get(self) -> list[RegistrySkill]:
        return list(self._stub_skills)

    @property
    def version(self) -> int:
        return id(self)


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


class TestSimilarityIndexCaching:
    """Proves the TF-IDF vectorizer is fit once per registry snapshot, not per request."""

    def test_index_is_reused_across_requests_against_same_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.main as main_module

        calls = {"n": 0}
        real_build = main_module.build_similarity_index

        def _counting_build(candidates: list[RegistrySkill]) -> object:
            calls["n"] += 1
            return real_build(candidates)

        monkeypatch.setattr(main_module, "build_similarity_index", _counting_build)
        client = _client(_StubCache([_ESCROW]))
        client.post("/check", json={"name": "A", "description": "anything"})
        client.post("/check", json={"name": "B", "description": "anything else"})
        client.post("/check", json={"name": "C", "description": "a third query"})
        assert calls["n"] == 1

    def test_index_rebuilds_when_cache_version_changes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.main as main_module

        calls = {"n": 0}
        real_build = main_module.build_similarity_index

        def _counting_build(candidates: list[RegistrySkill]) -> object:
            calls["n"] += 1
            return real_build(candidates)

        monkeypatch.setattr(main_module, "build_similarity_index", _counting_build)
        app.state.similarity_index = None
        app.state.similarity_index_version = -1

        client = _client(_StubCache([_ESCROW]))
        client.post("/check", json={"name": "A", "description": "anything"})

        # A fresh _StubCache is a different registry snapshot (new instance,
        # new id-based version) even though its content happens to match —
        # this is exactly the scenario the id()-based test double exists to
        # exercise safely instead of silently reusing a stale index.
        client2 = _client(_StubCache([_ESCROW]))
        client2.post("/check", json={"name": "B", "description": "anything"})
        assert calls["n"] == 2


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
    """Restore the real cache and clear the index cache after each test."""
    original = app.state.registry_cache
    yield
    app.state.registry_cache = original
    app.state.similarity_index = None
    app.state.similarity_index_version = -1
