from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from prama.evaluator import Evaluator, get_cer, get_wer
from prama.models import WerResult


def test_get_wer_evaluates_text_lists() -> None:
    result = get_wer(
        ["the quick brown fox jumps over the lazy dog"],
        ["the quick brown fox jumped over lazy dog"],
        ["sample-a"],
    )

    assert isinstance(result, WerResult)
    assert result.summary.ref_words == 9
    assert result.summary.correct == 7
    assert result.summary.substitutions == 1
    assert result.summary.deletions == 1
    assert result.summary.insertions == 0
    assert round(result.wer, 1) == 22.2
    assert result.groups[0].name == "(sample-a)"
    assert result.utterances[0].id == "(sample-a)"
    assert result.utterances[0].tokens[4].eval_label == "substitution"


def test_evaluator_evaluates_text_lists() -> None:
    with Evaluator() as evaluator:
        result = evaluator.get_wer(
            ["hello world", "speech recognition"],
            ["hello word", "speech recognition now"],
            ["short-hello", "asr-demo"],
        )

    assert result.summary.ref_words == 4
    assert result.summary.correct == 3
    assert result.summary.substitutions == 1
    assert result.summary.insertions == 1
    assert len(result.groups) == 2
    assert len(result.utterances) == 2
    assert [utterance.id for utterance in result.utterances] == ["(short-hello)", "(asr-demo)"]


def test_evaluator_reuses_client_until_closed() -> None:
    evaluator = Evaluator()
    first = evaluator.get_wer(["a b c"], ["a b"])
    second = evaluator.get_cer(["abc"], ["axc"])

    assert first.summary.deletions == 1
    assert second.summary.substitutions == 1
    assert second.metric == "cer"

    evaluator.close()
    try:
        evaluator.get_wer(["a"], ["a"])
    except RuntimeError as exc:
        assert "evaluator is closed" in str(exc)
    else:
        raise AssertionError("closed evaluator should not evaluate")


def test_get_cer_evaluates_plain_strings() -> None:
    result = get_cer(["hello world"], ["hello word"])

    assert result.metric == "cer"
    assert result.summary.ref_words == 10
    assert result.summary.correct == 9
    assert result.summary.deletions == 1
    assert result.summary.insertions == 0
    assert round(result.cer, 1) == 10.0


def test_get_cer_evaluates_unicode_strings() -> None:
    result = get_cer(["你好世界"], ["你好世"])

    assert result.summary.ref_words == 4
    assert result.summary.correct == 3
    assert result.summary.deletions == 1
    assert result.utterances[0].tokens[-1].ref_word == "界"
    assert result.utterances[0].tokens[-1].hyp_word is None


def test_evaluator_accepts_length_mismatch_as_empty_utterance() -> None:
    result = get_wer(["hello world"], [], ["missing-hyp"])

    assert result.summary.ref_words == 2
    assert result.summary.deletions == 2
    assert result.summary.insertions == 0


def test_evaluator_rejects_non_list_inputs() -> None:
    try:
        get_wer("hello", ["hello"])  # type: ignore[arg-type]
    except TypeError as exc:
        assert "references must be a List[str]" in str(exc)
    else:
        raise AssertionError("references must require List[str]")


def test_evaluator_rejects_invalid_utterance_ids() -> None:
    try:
        get_wer(["hello"], ["hello"], ["bad(id)"])
    except ValueError as exc:
        assert "utterance_ids must not contain parentheses or newlines" in str(exc)
    else:
        raise AssertionError("utterance ids must be TRN-safe")
