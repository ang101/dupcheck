"""Duplicate-Skill Checker — check a proposed skill against the live registry.

Routes are HTTP plumbing only; registry I/O lives in ``registry_client`` and
scoring logic in ``similarity``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.models import CheckRequest, CheckResponse, RegistrySkill
from app.registry_client import DEFAULT_REGISTRY_URL, RegistryCache, RegistryFetchError
from app.similarity import (
    SimilarityIndex,
    build_similarity_index,
    is_likely_duplicate,
    rank_duplicates,
    score_against_index,
)

SKILL_MD_PATH = Path(__file__).resolve().parent.parent / "SKILL.md"
REGISTRY_URL_ENV_VAR = "DUPCHECK_REGISTRY_URL"
"""Override for the registry endpoint — points local/dev instances at a
snapshot server; production leaves it unset for the live registry."""

app = FastAPI(
    title="Duplicate-Skill Checker",
    description=(
        "Check a proposed skill against every live entry in the NANDA Town "
        "registry before you build it — catch near-duplicates early."
    ),
    version="0.1.0",
)

app.state.registry_cache = RegistryCache(
    registry_url=os.environ.get(REGISTRY_URL_ENV_VAR, DEFAULT_REGISTRY_URL)
)
app.state.similarity_index = None
app.state.similarity_index_version = -1


def get_registry_cache(request: Request) -> RegistryCache:
    """Dependency: the process-lifetime registry cache."""
    cache: RegistryCache = request.app.state.registry_cache
    return cache


def _get_or_build_index(
    request: Request, cache: RegistryCache, skills: list[RegistrySkill]
) -> SimilarityIndex:
    """Return the cached TF-IDF index, rebuilding only when the registry actually refetched.

    ``RegistryCache.version`` only increments on a real network refresh
    (every 5 minutes), so the expensive vectorizer fit happens at most once
    per refresh instead of once per ``/check`` request — the caller already
    has ``skills`` from its own ``cache.get()`` call, so this never fetches
    the registry a second time.
    """
    state = request.app.state
    if state.similarity_index is None or state.similarity_index_version != cache.version:
        state.similarity_index = build_similarity_index(skills)
        state.similarity_index_version = cache.version
    index: SimilarityIndex = state.similarity_index
    return index


@app.post("/check", response_model=CheckResponse)
def check_skill(
    request: Request,
    body: CheckRequest,
    cache: Annotated[RegistryCache, Depends(get_registry_cache)],
) -> CheckResponse:
    """Rank live registry entries by similarity to the proposed skill."""
    try:
        skills = cache.get()
    except RegistryFetchError as exc:
        # 503, not a silent empty result: a duplicate check against no data
        # would wrongly green-light a real duplicate.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not skills:
        return CheckResponse(duplicates=[], is_likely_duplicate=False, registry_count=0)

    index = _get_or_build_index(request, cache, skills)
    scores = score_against_index(index, body.name, body.description)
    duplicates = rank_duplicates(skills, scores)
    return CheckResponse(
        duplicates=duplicates,
        is_likely_duplicate=is_likely_duplicate(duplicates),
        registry_count=len(skills),
    )


@app.get("/skill.md", response_class=PlainTextResponse)
def get_skill_md() -> PlainTextResponse:
    """Serve SKILL.md from disk per-request so edits appear without redeploy."""
    if not SKILL_MD_PATH.exists():
        raise HTTPException(status_code=404, detail="SKILL.md not found on server")
    return PlainTextResponse(SKILL_MD_PATH.read_text(encoding="utf-8"), media_type="text/markdown")


@app.get("/health")
def health(cache: Annotated[RegistryCache, Depends(get_registry_cache)]) -> dict[str, str]:
    """Liveness endpoint for the keepalive pinger; reports registry reachability.

    Also surfaces how many malformed registry entries were skipped on the
    last fetch, so degraded coverage is externally visible rather than silent.
    """
    try:
        count = len(cache.get())
    except RegistryFetchError as exc:
        return {"status": "degraded", "registry": f"unreachable: {exc}"}
    return {
        "status": "ok",
        "registry": f"{count} skills cached ({cache.skipped_count} malformed entries skipped)",
    }
