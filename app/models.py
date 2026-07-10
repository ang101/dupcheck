"""Pydantic models and the internal registry-entry shape."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
    """Body for ``POST /check`` — the skill you are thinking of building."""

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class DuplicateMatch(BaseModel):
    """One existing registry entry ranked as similar to the proposed skill."""

    id: str
    name: str
    similarity_score: float
    description: str


class CheckResponse(BaseModel):
    """Duplicate verdict for a proposed skill.

    ``registry_count`` reports how many live entries were compared against,
    so a caller can tell an empty-registry green from a real green.
    """

    duplicates: list[DuplicateMatch]
    is_likely_duplicate: bool
    registry_count: int


@dataclass(frozen=True)
class RegistrySkill:
    """One parsed entry from the live NANDA Town registry."""

    id: str
    name: str
    description: str
    tags: tuple[str, ...]
