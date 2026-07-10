"""Registry client parsing and cache tests — all network calls mocked."""

from __future__ import annotations

import httpx
import pytest

from app.registry_client import (
    RegistryCache,
    RegistryFetchError,
    fetch_registry,
    parse_registry_entry,
    parse_tags,
)

_VALID_ENTRY: dict[str, object] = {
    "id": "abc-123",
    "name": "  Town Notary  ",
    "description": " Badge verification and reputation ",
    "tags": "trust, reputation",
}


class TestParseTags:
    def test_comma_string_splits_and_strips(self) -> None:
        assert parse_tags("trust, reputation , escrow") == ("trust", "reputation", "escrow")

    def test_none_returns_empty_tuple(self) -> None:
        assert parse_tags(None) == ()

    def test_blank_string_returns_empty_tuple(self) -> None:
        assert parse_tags("   ") == ()


class TestParseRegistryEntry:
    def test_valid_entry_parses_and_strips_whitespace(self) -> None:
        skill = parse_registry_entry(_VALID_ENTRY)
        assert skill.name == "Town Notary"
        assert skill.description == "Badge verification and reputation"
        assert skill.tags == ("trust", "reputation")

    def test_missing_id_raises_value_error_naming_field(self) -> None:
        with pytest.raises(ValueError, match="'id'"):
            parse_registry_entry({"name": "X", "description": "Y"})

    def test_blank_description_raises_value_error(self) -> None:
        """The live registry really contains such entries (3 of 109 on 2026-07-10)."""
        with pytest.raises(ValueError, match="'description'"):
            parse_registry_entry({"id": "1", "name": "X", "description": "  "})


class TestFetchRegistry:
    def _patch_get(
        self, monkeypatch: pytest.MonkeyPatch, payload: object, status_code: int = 200
    ) -> None:
        monkeypatch.setattr(
            httpx.Client,
            "get",
            lambda self, *a, **kw: httpx.Response(status_code=status_code, json=payload),
        )

    def test_wrapped_skills_payload_parses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_get(monkeypatch, {"count": 1, "skills": [_VALID_ENTRY]})
        skills, skipped = fetch_registry("https://registry.example/api/skills")
        assert len(skills) == 1
        assert skipped == 0

    def test_malformed_entries_are_skipped_and_counted_not_fatal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad_entry = {"id": "2", "name": "Blank", "description": ""}
        self._patch_get(monkeypatch, {"count": 2, "skills": [_VALID_ENTRY, bad_entry]})
        skills, skipped = fetch_registry("https://registry.example/api/skills")
        assert len(skills) == 1
        assert skipped == 1

    def test_non_200_status_raises_registry_fetch_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_get(monkeypatch, {}, status_code=503)
        with pytest.raises(RegistryFetchError, match="503"):
            fetch_registry("https://registry.example/api/skills")

    def test_flat_array_payload_raises_registry_fetch_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The API is documented as wrapped; a shape change must be loud."""
        self._patch_get(monkeypatch, [_VALID_ENTRY])
        with pytest.raises(RegistryFetchError, match="shape"):
            fetch_registry("https://registry.example/api/skills")

    def test_network_error_raises_registry_fetch_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(self: httpx.Client, *a: object, **kw: object) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx.Client, "get", _raise)
        with pytest.raises(RegistryFetchError, match="failed to fetch"):
            fetch_registry("https://registry.example/api/skills")


class TestRegistryCache:
    def test_returns_cached_copy_within_ttl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def _fake_fetch(url: str) -> tuple[list[object], int]:
            calls["n"] += 1
            return [], 0

        monkeypatch.setattr("app.registry_client.fetch_registry", _fake_fetch)
        cache = RegistryCache("https://registry.example", ttl_seconds=300)
        cache.get()
        cache.get()
        assert calls["n"] == 1

    def test_refetches_after_ttl_expires(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def _fake_fetch(url: str) -> tuple[list[object], int]:
            calls["n"] += 1
            return [], 0

        # Fake the clock too: Windows' monotonic resolution is coarse enough
        # that two immediate calls can see identical timestamps, making a
        # real-clock ttl=0 test flaky.
        fake_now = {"t": 1000.0}
        monkeypatch.setattr("app.registry_client.fetch_registry", _fake_fetch)
        monkeypatch.setattr("app.registry_client.time.monotonic", lambda: fake_now["t"])
        cache = RegistryCache("https://registry.example", ttl_seconds=300)
        cache.get()
        fake_now["t"] += 301.0
        cache.get()
        assert calls["n"] == 2

    def test_returned_list_is_a_copy_not_internal_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        skill = parse_registry_entry(_VALID_ENTRY)

        monkeypatch.setattr("app.registry_client.fetch_registry", lambda url: ([skill], 0))
        cache = RegistryCache("https://registry.example", ttl_seconds=300)
        first = cache.get()
        first.clear()
        assert len(cache.get()) == 1
