"""Similarity scoring and ranking tests."""

from __future__ import annotations

import pytest

from app.models import RegistrySkill
from app.similarity import (
    build_corpus_texts,
    compute_similarity_scores,
    is_likely_duplicate,
    rank_duplicates,
)


def _skill(skill_id: str, name: str, description: str) -> RegistrySkill:
    return RegistrySkill(id=skill_id, name=name, description=description, tags=())


_ESCROW = _skill("1", "AgentCourt Escrow", "Secure agent escrow and dispute resolution")
_WEATHER = _skill("2", "TribeHeat", "World Cup crowd heat map for fans")
_ESCROW_CLONE = _skill(
    "3", "Agent Escrow Court", "Escrow and dispute resolution for secure agent payments"
)


class TestComputeSimilarityScores:
    def test_identical_name_and_description_scores_near_one(self) -> None:
        scores = compute_similarity_scores(
            "AgentCourt Escrow", "Secure agent escrow and dispute resolution", [_ESCROW]
        )
        assert scores[0] > 0.99

    def test_unrelated_text_scores_near_zero(self) -> None:
        scores = compute_similarity_scores(
            "Recipe Recommender", "Suggests dinner recipes from pantry contents", [_WEATHER]
        )
        assert scores[0] < 0.1

    def test_paraphrased_description_scores_higher_than_unrelated(self) -> None:
        scores = compute_similarity_scores(
            "Escrow Service",
            "Dispute resolution and escrow for agent payments",
            [_ESCROW_CLONE, _WEATHER],
        )
        assert scores[0] > scores[1]

    def test_empty_candidates_list_returns_empty_scores(self) -> None:
        assert compute_similarity_scores("X", "anything at all", []) == []

    def test_single_candidate_returns_single_score(self) -> None:
        scores = compute_similarity_scores("X", "anything at all", [_ESCROW])
        assert len(scores) == 1

    def test_scores_are_in_candidate_order(self) -> None:
        scores = compute_similarity_scores(
            "crowd heat map", "world cup fans crowd map", [_ESCROW, _WEATHER]
        )
        assert scores[1] > scores[0]


class TestBuildCorpusTexts:
    def test_combines_name_and_description(self) -> None:
        assert build_corpus_texts([_ESCROW]) == [
            "AgentCourt Escrow Secure agent escrow and dispute resolution"
        ]

    def test_empty_input_returns_empty_list(self) -> None:
        assert build_corpus_texts([]) == []


class TestRankDuplicates:
    def test_filters_below_min_score(self) -> None:
        matches = rank_duplicates([_ESCROW, _WEATHER], [0.9, 0.05], min_score=0.30)
        assert [m.id for m in matches] == ["1"]

    def test_sorts_descending_by_score(self) -> None:
        matches = rank_duplicates([_ESCROW, _ESCROW_CLONE], [0.5, 0.9], min_score=0.30)
        assert [m.id for m in matches] == ["3", "1"]

    def test_respects_top_k_limit(self) -> None:
        candidates = [_skill(str(i), f"Skill {i}", "same description text here") for i in range(9)]
        matches = rank_duplicates(candidates, [0.9] * 9, top_k=5)
        assert len(matches) == 5

    def test_mismatched_lengths_raise_value_error(self) -> None:
        with pytest.raises(ValueError, match="candidates"):
            rank_duplicates([_ESCROW], [0.5, 0.9])

    def test_empty_inputs_return_empty_list(self) -> None:
        assert rank_duplicates([], []) == []


class TestIsLikelyDuplicate:
    def test_true_when_any_match_at_or_above_threshold(self) -> None:
        matches = rank_duplicates([_ESCROW], [0.75], min_score=0.30)
        assert is_likely_duplicate(matches, threshold=0.60)

    def test_false_when_all_matches_below_threshold(self) -> None:
        matches = rank_duplicates([_ESCROW], [0.45], min_score=0.30)
        assert not is_likely_duplicate(matches, threshold=0.60)

    def test_false_for_no_matches(self) -> None:
        assert not is_likely_duplicate([])
