"""TF-IDF similarity scoring between a proposed skill and registry entries.

TF-IDF + cosine is a deliberate choice over embeddings for this service:
zero cost, zero external dependency, no cold-start model download on a
free-tier host, and no rate limit on a public unauthenticated endpoint.
The tradeoff — lexical rather than semantic matching — is documented in
the README; the isolation of scoring behind one function makes an
embeddings swap a drop-in change later.
"""

from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity  # pyright: ignore[reportUnknownVariableType]

from app.models import DuplicateMatch, RegistrySkill

MAX_DUPLICATE_RESULTS = 5
"""At ~100 registry entries, more than a handful of matches stops being a
shortlist and starts being noise."""

SIMILARITY_MATCH_FLOOR = 0.30
"""Scores below this are incidental vocabulary overlap, not candidate
duplicates. Tuned against all pairwise similarities in the live registry
(2026-07-10, 106 parseable entries): the unrelated-pair distribution sits
at p95 = 0.103 and p99 = 0.266, so 0.30 clears ~99% of noise pairs."""

LIKELY_DUPLICATE_THRESHOLD = 0.45
"""A single match at or above this makes the proposal a likely duplicate.
Tuned against every pairwise similarity in the live registry (2026-07-10):
the >= 0.45 population is dominated by true duplicates — 16 literal
resubmission pairs at exactly 1.0, near-identical rewordings at 0.76-0.90,
and same-skill-edited-description resubmissions at 0.46-0.59 (Testament/
TESTAMENT 0.543, LEX AUTOMATA/lex-automata 0.462, Town Notary 0.550,
Pareto 0.592). The 0.40-0.43 band below the cut is where genuinely distinct
same-niche competitors live (e.g. two different escrow-arbitration skills
at 0.426) — those stay listed as prior art without the hard verdict."""


def build_corpus_texts(skills: list[RegistrySkill]) -> list[str]:
    """Combine each entry's name and description into one comparison text.

    Tags are deliberately excluded: they are optional, inconsistently used
    across the registry, and shared tags (e.g. 'payments') would inflate
    similarity between genuinely different skills.

    Example::

        texts = build_corpus_texts(skills)
        assert len(texts) == len(skills)
    """
    return [f"{skill.name} {skill.description}" for skill in skills]


def compute_similarity_scores(
    query_name: str,
    query_description: str,
    candidates: list[RegistrySkill],
) -> list[float]:
    """Cosine similarity of the proposed skill against every candidate.

    Returns one score per candidate, in candidate order. An empty candidate
    list returns ``[]`` — an empty registry is a legitimate state, not an
    error.

    Example::

        scores = compute_similarity_scores("My Skill", "does things", skills)
    """
    if not candidates:
        return []
    corpus = build_corpus_texts(candidates)
    query_text = f"{query_name} {query_description}"
    vectorizer = TfidfVectorizer(stop_words="english")
    # sklearn ships no type information; suppressions are scoped to the calls.
    matrix = vectorizer.fit_transform([*corpus, query_text])  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    similarities = cosine_similarity(matrix[-1:], matrix[:-1])[0]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType, reportUnknownMemberType, reportIndexIssue]
    return [float(score) for score in similarities]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]


def rank_duplicates(
    candidates: list[RegistrySkill],
    scores: list[float],
    top_k: int = MAX_DUPLICATE_RESULTS,
    min_score: float = SIMILARITY_MATCH_FLOOR,
) -> list[DuplicateMatch]:
    """Filter to scores above the floor, sort descending, keep the top K.

    Raises ``ValueError`` if the two lists disagree in length — that is a
    caller bug that would silently mispair skills with scores.

    Example::

        matches = rank_duplicates(skills, scores)
    """
    if len(candidates) != len(scores):
        msg = f"got {len(candidates)} candidates but {len(scores)} scores"
        raise ValueError(msg)
    scored = [
        DuplicateMatch(
            id=skill.id,
            name=skill.name,
            similarity_score=round(score, 4),
            description=skill.description,
        )
        for skill, score in zip(candidates, scores, strict=True)
        if score >= min_score
    ]
    scored.sort(key=lambda match: match.similarity_score, reverse=True)
    return scored[:top_k]


def is_likely_duplicate(
    duplicates: list[DuplicateMatch],
    threshold: float = LIKELY_DUPLICATE_THRESHOLD,
) -> bool:
    """True when any ranked match clears the likely-duplicate threshold.

    Example::

        assert is_likely_duplicate(matches) in (True, False)
    """
    return any(match.similarity_score >= threshold for match in duplicates)
