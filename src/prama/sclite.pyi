from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path


class ScliteError(RuntimeError): ...


class Format(IntEnum):
    TRN: int
    STM: int
    CTM: int
    TXT: int


class IdType(IntEnum):
    WSJ: int
    RM: int
    ATIS: int
    SWB: int
    SPU_ID: int
    SP: int


class ReportType(IntEnum):
    SYS: int
    RAW: int
    PRA: int
    PRF: int
    SGML: int


@dataclass(slots=True)
class ScliteOptions:
    title: str | None = ...
    id_type: IdType = ...
    encoding: str | None = ...
    language_profile: str | None = ...
    case_sensitive: bool = ...
    char_align_flags: int = ...
    fragment_correct: bool = ...
    optional_deletion: bool = ...
    time_align: bool = ...
    left_to_right: bool = ...
    infer_word_seg: bool = ...
    lexicon_path: str | Path | None = ...
    infer_flags: int = ...
    reduce_ref_segments: bool = ...
    reduce_hyp_words: bool = ...
    wwl_path: str | Path | None = ...
    lm_path: str | Path | None = ...
    feedback: int = ...


@dataclass(frozen=True, slots=True)
class ScliteCounts:
    ref_words: int
    hyp_words: int
    correct: int
    substitutions: int
    deletions: int
    insertions: int
    sentence_count: int
    sentence_errors: int
    wer: float
    accuracy: float


@dataclass(frozen=True, slots=True)
class ScliteGroup:
    name: str
    counts: ScliteCounts


@dataclass(frozen=True, slots=True)
class ScliteUtterance:
    id: str
    labels: str
    file: str
    channel: str
    ref_start: float
    ref_end: float
    hyp_start: float
    hyp_end: float
    token_count: int


@dataclass(frozen=True, slots=True)
class ScliteToken:
    eval: int
    eval_label: str
    ref_word: str | None
    hyp_word: str | None
    ref_start: float
    ref_end: float
    hyp_start: float
    hyp_end: float
    ref_conf: float
    hyp_conf: float
    ref_weight: float
    hyp_weight: float


def find_sclite_library(lib_path: str | Path | None = None) -> Path: ...


class ScliteClient:
    lib_path: str | Path

    def __init__(self, lib_path: str | Path | None = None) -> None: ...
    def close(self) -> None: ...
    def __enter__(self) -> ScliteClient: ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...
    def align_texts(
        self,
        ref_data: str | bytes,
        hyp_data: str | bytes,
        *,
        ref_format: Format | str | int,
        hyp_format: Format | str | int,
        options: ScliteOptions | None = None,
    ) -> ScliteResult: ...
    def align_files(
        self,
        ref_path: str | Path,
        hyp_path: str | Path,
        *,
        ref_format: Format | str | int,
        hyp_format: Format | str | int,
        options: ScliteOptions | None = None,
    ) -> ScliteResult: ...


class ScliteResult:
    def close(self) -> None: ...
    def __enter__(self) -> ScliteResult: ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...
    def summary(self) -> ScliteCounts: ...
    def groups(self) -> list[ScliteGroup]: ...
    def utterances(self, group_index: int = 0) -> list[ScliteUtterance]: ...
    def tokens(self, group_index: int = 0, utterance_index: int = 0) -> list[ScliteToken]: ...
    def report_text(self, report_type: ReportType | str | int = ReportType.PRA) -> str: ...
