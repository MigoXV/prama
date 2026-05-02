from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from prama.sclite import Format, IdType, ScliteClient, ScliteOptions


DATA_DIR = ROOT / "data-bin" / "sclite"
MODEL_SCLITE = ROOT / "model-bin" / "sclite" / "sclite"


def _run_original(*args: str | Path) -> tuple[int, int, int, int, int, int]:
    completed = subprocess.run(
        [str(MODEL_SCLITE), *map(str, args)],
        check=True,
        text=True,
        capture_output=True,
    )
    match = re.search(
        r"\|\s*Sum\s+\|\s+\d+\s+(\d+)\s+\|\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
        completed.stdout,
    )
    if match is None:
        raise AssertionError(f"could not parse original sclite output:\n{completed.stdout}")
    ref_words, correct, substitutions, deletions, insertions = map(int, match.groups())
    return ref_words, ref_words, correct, substitutions, deletions, insertions


def _summary_tuple(result: object) -> tuple[int, int, int, int, int, int]:
    counts = result.summary()
    return (
        counts.ref_words,
        counts.hyp_words,
        counts.correct,
        counts.substitutions,
        counts.deletions,
        counts.insertions,
    )


def test_trn_wrapper_matches_original_sclite() -> None:
    expected = _run_original(
        "-r",
        DATA_DIR / "ref.trn",
        "trn",
        "-h",
        DATA_DIR / "hyp.trn",
        "trn",
        "-i",
        "sp",
        "-o",
        "all",
        "stdout",
    )
    with ScliteClient() as client:
        with client.align_files(
            DATA_DIR / "ref.trn",
            DATA_DIR / "hyp.trn",
            ref_format=Format.TRN,
            hyp_format=Format.TRN,
            options=ScliteOptions(id_type=IdType.SP),
        ) as result:
            assert _summary_tuple(result) == expected
            assert round(result.summary().wer, 1) == 20.7


def test_stm_ctm_wrapper_matches_original_sclite() -> None:
    expected = _run_original(
        "-r",
        DATA_DIR / "ref.stm",
        "stm",
        "-h",
        DATA_DIR / "hyp.ctm",
        "ctm",
        "-o",
        "all",
        "stdout",
    )
    with ScliteClient() as client:
        with client.align_files(
            DATA_DIR / "ref.stm",
            DATA_DIR / "hyp.ctm",
            ref_format="stm",
            hyp_format="ctm",
        ) as result:
            assert _summary_tuple(result) == expected
            groups = result.groups()
            assert [group.name for group in groups] == ["speaker_a", "speaker_b"]


def test_missing_library_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="libsclite.so not found"):
        ScliteClient(lib_path=tmp_path / "missing" / "libsclite.so")


def test_invalid_format_raises_value_error() -> None:
    with ScliteClient() as client:
        with pytest.raises(ValueError, match="unsupported sclite format"):
            client.align_files(
                DATA_DIR / "ref.trn",
                DATA_DIR / "hyp.trn",
                ref_format="bad",
                hyp_format="trn",
            )
