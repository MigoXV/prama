from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from prama.sclite import IdType, ScliteClient, ScliteError, ScliteOptions
from scripts.check_alignment import check_case

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def original():
    executable = Path(
        os.environ.get("SCLITE_REFERENCE", ROOT / "build/original/sclite/sclite")
    )
    if not executable.exists():
        if not (ROOT / "tmo-workspace/SCTK/src/sclite").exists():
            pytest.skip(
                "set SCLITE_REFERENCE to an independently compiled original sclite"
            )
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_reference.py")],
            cwd=ROOT,
            check=True,
        )
    return executable


@pytest.mark.parametrize(
    "ref,hyp",
    [
        ("a b c (s_1)\n", "a x c d (s_1)\n"),
        ("(s_1)\na (s_2)\n", "x (s_1)\n(s_2)\n"),
        ("a b a (s_1)\na (t_1)\nb (s_2)\n", "a a b (s_1)\nb (t_1)\nb c (s_2)\n"),
        ("a { b / c } d (s_1)\n", "a c d (s_1)\n"),
        ("你 好 世界 café 🙂 (s_1)\n", "你 好 世 cafe 🙂 (s_1)\n"),
    ],
)
@pytest.mark.parametrize("character", [False, True])
def test_trn_matches_original(original, ref, hyp, character):
    check_case(
        original,
        ref,
        hyp,
        options=ScliteOptions(encoding="UTF-8", char_align_flags=int(character)),
        flags=["-c"] if character else [],
    )


@pytest.mark.parametrize(
    "options,flags",
    [
        (ScliteOptions(encoding="UTF-8", case_sensitive=True), ["-s"]),
        (ScliteOptions(encoding="UTF-8", optional_deletion=True), ["-D"]),
        (ScliteOptions(encoding="UTF-8", fragment_correct=True), ["-F"]),
    ],
)
def test_options_match_original(original, options, flags):
    check_case(
        original,
        "Hello (WORLD) par- (s_1)\n",
        "hello part (s_1)\n",
        options=options,
        flags=flags,
    )


@pytest.mark.parametrize("time_align", [False, True])
def test_ctm_matches_original(original, time_align):
    ref = "f A 0.0 0.5 hello 0.9\nf A 0.5 0.5 world 0.8\n"
    hyp = "f A 0.0 0.5 hello 0.95\nf A 0.5 0.5 word 0.7\n"
    check_case(
        original,
        ref,
        hyp,
        ref_format="ctm",
        hyp_format="ctm",
        options=ScliteOptions(encoding="UTF-8", time_align=time_align),
        flags=["-T"] if time_align else [],
    )


def test_stm_ctm_matches_original(original):
    ref = "f A speaker_a 0.0 1.0 <O> hello world\nf A speaker_b 1.0 2.0 <O> good bye\n"
    hyp = "f A 0.0 0.4 hello 0.9\nf A 0.5 0.4 word 0.8\nf A 1.0 0.4 good 0.9\n"
    check_case(original, ref, hyp, ref_format="stm", hyp_format="ctm")


def test_missing_library_raises_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="libsclite.so not found"):
        ScliteClient(tmp_path / "missing.so")


def test_invalid_input_does_not_exit_and_client_recovers():
    with ScliteClient() as client:
        for _ in range(5):
            with pytest.raises(ScliteError):
                client.align_texts(
                    "a (s_1)\n",
                    "a (s_1)\nb (missing)\n",
                    ref_format="trn",
                    hyp_format="trn",
                )
            with client.align_texts(
                "a (s_1)\n", "a (s_1)\n", ref_format="trn", hyp_format="trn"
            ) as result:
                assert result.summary().correct == 1


def test_result_survives_client_and_is_guarded_after_close():
    with ScliteClient() as client:
        result = client.align_texts(
            "a (s_1)\n", "a (s_1)\n", ref_format="trn", hyp_format="trn"
        )
    assert result.summary().correct == 1
    assert "a" in result.report_text()
    result.close()
    result.close()
    with pytest.raises(ScliteError, match="closed"):
        result.tokens()


@pytest.mark.parametrize(
    "options",
    [
        ScliteOptions(encoding="invalid"),
        ScliteOptions(language_profile="invalid"),
        ScliteOptions(lm_path="missing"),
        ScliteOptions(time_align=True),
        ScliteOptions(char_align_flags=8),
    ],
)
def test_invalid_options_rejected(options):
    with ScliteClient() as c, pytest.raises(ScliteError):
        c.align_texts(
            "a (s_1)\n",
            "a (s_1)\n",
            ref_format="trn",
            hyp_format="trn",
            options=options,
        )


@pytest.mark.parametrize(
    "ref,hyp,rf,hf,options,flags",
    [
        (
            "csrnab.ref",
            "csrnab.hyp",
            "trn",
            "trn",
            ScliteOptions(id_type=IdType.WSJ, encoding="UTF-8"),
            [],
        ),
        (
            "lvc_ref.stm",
            "lvc_hyp.ctm",
            "stm",
            "ctm",
            ScliteOptions(encoding="UTF-8"),
            [],
        ),
        (
            "lvc_refe.stm",
            "lvc_hyp.ctm",
            "stm",
            "ctm",
            ScliteOptions(encoding="UTF-8"),
            [],
        ),
        (
            "lvc_ref.stm",
            "lvc_hypc.ctm",
            "stm",
            "ctm",
            ScliteOptions(encoding="UTF-8"),
            [],
        ),
        (
            "tests.ref",
            "tests.hyp",
            "trn",
            "trn",
            ScliteOptions(
                encoding="UTF-8", fragment_correct=True, optional_deletion=True
            ),
            ["-F", "-D"],
        ),
    ],
)
def test_upstream_corpus(original, ref, hyp, rf, hf, options, flags):
    data = ROOT / "tests/data/upstream"
    check_case(
        original,
        (data / ref).read_text(),
        (data / hyp).read_text(),
        ref_format=rf,
        hyp_format=hf,
        options=options,
        flags=flags,
    )


@pytest.mark.parametrize("algorithm", [1, 2])
@pytest.mark.parametrize("ascii_too", [0, 1])
def test_inferred_segmentation(original, algorithm, ascii_too):
    data = ROOT / "tests/data/upstream"
    lexicon = data / "tests.lex"
    options = ScliteOptions(
        encoding="UTF-8",
        infer_word_seg=algorithm,
        lexicon_path=lexicon,
        infer_flags=ascii_too,
    )
    flags = ["-S", f"algo{algorithm}", str(lexicon)] + (
        ["ASCIITOO"] if ascii_too else []
    )
    check_case(
        original,
        (data / "tests.ref").read_text(),
        (data / "tests.hyp").read_text(),
        options=options,
        flags=flags,
    )


def test_weighted_alignment(original):
    data = ROOT / "tests/data/upstream"
    weights = data / "csrnab_r.wwl"
    check_case(
        original,
        (data / "csrnab.ref").read_text(),
        (data / "csrnab.hyp").read_text(),
        options=ScliteOptions(encoding="UTF-8", id_type=IdType.WSJ, wwl_path=weights),
        flags=["-w", str(weights)],
    )


def test_long_record_id_and_long_token():
    text = "z" * 3000
    record_id = "speaker" * 300 + "_1"
    with (
        ScliteClient() as c,
        c.align_texts(
            f"{text} ({record_id})\n",
            f"{text} ({record_id})\n",
            ref_format="trn",
            hyp_format="trn",
        ) as r,
    ):
        assert r.summary().correct == 1
        assert r.utterances()[0].id == f"({record_id})"
        assert r.tokens()[0].ref_word == text


@pytest.mark.parametrize("bad", ["a )b(\n", "a (\n", "a (no_separator)\n\x00"])
def test_malformed_ids_and_nul_rejected(bad):
    with ScliteClient() as c, pytest.raises(ScliteError):
        c.align_texts(bad, bad, ref_format="trn", hyp_format="trn")


def test_live_results_and_unicode_report_isolation():
    with ScliteClient() as c:
        with c.align_texts(
            "café (s_1)\n",
            "x (s_1)\n",
            ref_format="trn",
            hyp_format="trn",
            options=ScliteOptions(encoding="UTF-8"),
        ) as first:
            before = first.report_text()
            with c.align_texts(
                "A (s_1)\n",
                "a (s_1)\n",
                ref_format="trn",
                hyp_format="trn",
                options=ScliteOptions(case_sensitive=True),
            ) as second:
                assert second.summary().substitutions == 1
                assert first.report_text() == before
