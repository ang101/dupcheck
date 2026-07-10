"""Client for the live NANDA Town skills registry.

The registry endpoint returns a wrapped object ``{"count": N, "skills": [...]}``
(confirmed against the live API on 2026-07-10, 109 entries) — not a flat
array. Each entry carries ``id``/``name``/``description``/``tags`` among
other fields; ``tags`` is a comma-separated string, not a list. The live
data includes entries with blank descriptions (3 of 109 on 2026-07-10), so
per-entry parse failures are skipped-and-counted rather than fatal — one
builder's malformed submission must not take this whole service down.
"""

from __future__ import annotations

import json
import logging
import time
from typing import cast

import httpx

from app.models import RegistrySkill

logger = logging.getLogger("dupcheck")

DEFAULT_REGISTRY_URL = "https://nandatown.projectnanda.org/api/skills"
FETCH_TIMEOUT_SECONDS = 10.0
REGISTRY_CACHE_TTL_SECONDS = 300
"""Fetch-on-request with a short TTL rather than a background refresher: at
~100 entries a full fetch is cheap, and a scheduler thread would just die on
every free-tier dyno sleep anyway."""


class RegistryFetchError(Exception):
    """Raised when the live registry cannot be fetched or parsed.

    Carries the URL and cause so callers can surface an actionable error
    instead of a silent empty result.
    """


def parse_tags(raw_tags: object) -> tuple[str, ...]:
    """Split the registry's comma-separated tag string into clean tags.

    ``None``/empty input is a legitimate state (tags are optional in the
    registry), not an error.

    Example::

        assert parse_tags("escrow, payments") == ("escrow", "payments")
    """
    if not isinstance(raw_tags, str) or not raw_tags.strip():
        return ()
    return tuple(tag.strip() for tag in raw_tags.split(",") if tag.strip())


def parse_registry_entry(raw: dict[str, object]) -> RegistrySkill:
    """Validate and convert one raw registry entry.

    Raises ``ValueError`` naming the specific missing/blank field — a
    malformed entry must be visible, not silently skipped into a wrong
    similarity result.

    Example::

        skill = parse_registry_entry({"id": "1", "name": "X", "description": "..."})
    """
    for field in ("id", "name", "description"):
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            msg = f"registry entry missing or blank required field {field!r}: {raw.get('id')!r}"
            raise ValueError(msg)
    return RegistrySkill(
        id=str(raw["id"]).strip(),
        name=str(raw["name"]).strip(),
        description=str(raw["description"]).strip(),
        tags=parse_tags(raw.get("tags")),
    )


def fetch_registry(
    registry_url: str = DEFAULT_REGISTRY_URL,
    timeout_seconds: float = FETCH_TIMEOUT_SECONDS,
) -> tuple[list[RegistrySkill], int]:
    """Fetch the live registry, returning ``(parsed_skills, skipped_count)``.

    Raises ``RegistryFetchError`` on network failure, non-200, or a response
    shape that isn't the documented ``{"skills": [...]}`` wrapper. Individual
    malformed entries (the live registry really contains some — blank
    descriptions) are skipped, logged, and counted rather than fatal:
    another builder's bad submission must not break every duplicate check.

    Example::

        skills, skipped = fetch_registry()
        assert all(s.name for s in skills)
    """
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(registry_url)
    except httpx.HTTPError as exc:
        msg = f"failed to fetch registry from {registry_url}: {exc}"
        raise RegistryFetchError(msg) from exc

    if response.status_code != 200:
        msg = f"registry at {registry_url} returned HTTP {response.status_code}"
        raise RegistryFetchError(msg)

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        msg = f"registry at {registry_url} returned invalid JSON: {exc}"
        raise RegistryFetchError(msg) from exc

    if not isinstance(payload, dict):
        msg = f"registry at {registry_url} response is not the expected {{'skills': [...]}} shape"
        raise RegistryFetchError(msg)
    payload_dict = cast("dict[str, object]", payload)
    if not isinstance(payload_dict.get("skills"), list):
        msg = f"registry at {registry_url} response is not the expected {{'skills': [...]}} shape"
        raise RegistryFetchError(msg)

    entries = cast("list[dict[str, object]]", payload_dict["skills"])
    skills: list[RegistrySkill] = []
    skipped = 0
    for entry in entries:
        try:
            skills.append(parse_registry_entry(entry))
        except ValueError as exc:
            skipped += 1
            logger.warning("skipping malformed registry entry: %s", exc)
    return skills, skipped


class RegistryCache:
    """Process-lifetime cache of the parsed registry with a short TTL.

    A class (not functions) because the fetched entries and timestamp are
    state that persists across requests. Instantiated once in ``main.py``
    and injected via FastAPI dependencies.
    """

    def __init__(
        self,
        registry_url: str = DEFAULT_REGISTRY_URL,
        ttl_seconds: int = REGISTRY_CACHE_TTL_SECONDS,
    ) -> None:
        self._registry_url = registry_url
        self._ttl_seconds = ttl_seconds
        self._entries: list[RegistrySkill] = []
        self._skipped = 0
        self._fetched_at: float | None = None

    @property
    def skipped_count(self) -> int:
        """How many malformed entries the last fetch skipped (surfaced via /health).

        Example::

            assert cache.skipped_count >= 0
        """
        return self._skipped

    def get(self) -> list[RegistrySkill]:
        """Return the cached registry, refetching if stale or never fetched.

        Returns a copy so callers can never mutate the cache's internal list.
        Propagates ``RegistryFetchError`` on a failed refresh — a stale-but-
        present cache is NOT silently served past its TTL, because a duplicate
        check against a stale registry could green-light a real duplicate.

        Example::

            skills = cache.get()
        """
        now = time.monotonic()
        if self._fetched_at is None or (now - self._fetched_at) > self._ttl_seconds:
            self._entries, self._skipped = fetch_registry(self._registry_url)
            self._fetched_at = now
        return list(self._entries)
