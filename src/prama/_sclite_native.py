from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path
from typing import Iterable


LIB_ENV_VAR = "SCLITE_LIB_PATH"
LIB_FILENAME = "libsclite.so"


class COptions(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_int),
        ("struct_size", ctypes.c_int),
        ("title", ctypes.c_char_p),
        ("id_type", ctypes.c_int),
        ("encoding", ctypes.c_char_p),
        ("language_profile", ctypes.c_char_p),
        ("case_sensitive", ctypes.c_int),
        ("char_align_flags", ctypes.c_int),
        ("fragment_correct", ctypes.c_int),
        ("optional_deletion", ctypes.c_int),
        ("time_align", ctypes.c_int),
        ("left_to_right", ctypes.c_int),
        ("infer_word_seg", ctypes.c_int),
        ("lexicon_path", ctypes.c_char_p),
        ("infer_flags", ctypes.c_int),
        ("reduce_ref_segments", ctypes.c_int),
        ("reduce_hyp_words", ctypes.c_int),
        ("wwl_path", ctypes.c_char_p),
        ("lm_path", ctypes.c_char_p),
        ("feedback", ctypes.c_int),
    ]


class CCounts(ctypes.Structure):
    _fields_ = [
        ("ref_words", ctypes.c_int),
        ("hyp_words", ctypes.c_int),
        ("correct", ctypes.c_int),
        ("substitutions", ctypes.c_int),
        ("deletions", ctypes.c_int),
        ("insertions", ctypes.c_int),
        ("sentence_count", ctypes.c_int),
        ("sentence_errors", ctypes.c_int),
        ("wer", ctypes.c_double),
        ("accuracy", ctypes.c_double),
    ]


class CUtterance(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_char_p),
        ("labels", ctypes.c_char_p),
        ("file", ctypes.c_char_p),
        ("channel", ctypes.c_char_p),
        ("ref_start", ctypes.c_double),
        ("ref_end", ctypes.c_double),
        ("hyp_start", ctypes.c_double),
        ("hyp_end", ctypes.c_double),
        ("token_count", ctypes.c_int),
    ]


class CToken(ctypes.Structure):
    _fields_ = [
        ("eval", ctypes.c_int),
        ("ref_word", ctypes.c_char_p),
        ("hyp_word", ctypes.c_char_p),
        ("ref_start", ctypes.c_double),
        ("ref_end", ctypes.c_double),
        ("hyp_start", ctypes.c_double),
        ("hyp_end", ctypes.c_double),
        ("ref_conf", ctypes.c_double),
        ("hyp_conf", ctypes.c_double),
        ("ref_weight", ctypes.c_double),
        ("hyp_weight", ctypes.c_double),
    ]


def candidate_lib_paths(explicit_path: str | Path | None) -> Iterable[str | Path]:
    if explicit_path is not None:
        yield Path(explicit_path)
        return

    env_path = os.environ.get(LIB_ENV_VAR)
    if env_path:
        yield Path(env_path)

    package_root = Path(__file__).resolve().parent
    yield package_root / "lib" / LIB_FILENAME

    system_path = ctypes.util.find_library("sclite")
    if system_path:
        yield system_path


def find_sclite_library(lib_path: str | Path | None = None) -> str | Path:
    checked: list[str] = []
    for candidate in candidate_lib_paths(lib_path):
        checked.append(str(candidate))
        if isinstance(candidate, Path):
            if candidate.is_file():
                return candidate
            continue
        return candidate
    raise FileNotFoundError(f"{LIB_FILENAME} not found. Checked: {', '.join(checked)}")


def load_sclite_library(lib_path: str | Path | None = None) -> tuple[ctypes.CDLL, str | Path]:
    resolved_path = find_sclite_library(lib_path)
    library = ctypes.CDLL(str(resolved_path))
    configure_library(library)
    return library, resolved_path


def configure_library(library: ctypes.CDLL) -> None:
    library.sclite_context_new.restype = ctypes.c_void_p
    library.sclite_context_free.argtypes = [ctypes.c_void_p]
    library.sclite_options_init.argtypes = [ctypes.POINTER(COptions)]
    library.sclite_align_texts.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_int,
        ctypes.POINTER(COptions),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    library.sclite_align_texts.restype = ctypes.c_int
    library.sclite_context_error.argtypes = [ctypes.c_void_p]
    library.sclite_context_error.restype = ctypes.c_char_p
    library.sclite_result_free.argtypes = [ctypes.c_void_p]
    library.sclite_result_summary.argtypes = [ctypes.c_void_p, ctypes.POINTER(CCounts)]
    library.sclite_result_summary.restype = ctypes.c_int
    library.sclite_result_group_count.argtypes = [ctypes.c_void_p]
    library.sclite_result_group_count.restype = ctypes.c_int
    library.sclite_result_group_summary.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_char_p),
        ctypes.POINTER(CCounts),
    ]
    library.sclite_result_group_summary.restype = ctypes.c_int
    library.sclite_result_utterance_count.argtypes = [ctypes.c_void_p, ctypes.c_int]
    library.sclite_result_utterance_count.restype = ctypes.c_int
    library.sclite_result_utterance.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(CUtterance),
    ]
    library.sclite_result_utterance.restype = ctypes.c_int
    library.sclite_result_token.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(CToken),
    ]
    library.sclite_result_token.restype = ctypes.c_int
    library.sclite_result_report_text.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    library.sclite_result_report_text.restype = ctypes.c_int
    library.sclite_free_string.argtypes = [ctypes.c_void_p]
