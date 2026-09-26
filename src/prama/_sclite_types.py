from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path


class ScliteError(RuntimeError):
    """Raised when the sclite shared library reports an error."""


class Format(IntEnum):
    TRN = 1
    STM = 2
    CTM = 3
    TXT = 4


class IdType(IntEnum):
    WSJ = 1
    RM = 2
    ATIS = 3
    SWB = 4
    SPU_ID = 5
    SP = 6


class ReportType(IntEnum):
    SYS = 1
    RAW = 2
    PRA = 3
    PRF = 4
    SGML = 5


@dataclass(slots=True)
class ScliteOptions:
    title: str | None = None
    id_type: IdType = IdType.SPU_ID
    encoding: str | None = None
    language_profile: str | None = None
    case_sensitive: bool = False
    char_align_flags: int = 0
    fragment_correct: bool = False
    optional_deletion: bool = False
    time_align: bool = False
    left_to_right: bool = True
    infer_word_seg: int = 0
    lexicon_path: str | Path | None = None
    infer_flags: int = 0
    reduce_ref_segments: bool = False
    reduce_hyp_words: bool = False
    wwl_path: str | Path | None = None
    lm_path: str | Path | None = None
    feedback: int = 0


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


FORMAT_BY_NAME = {
    "trn": Format.TRN,
    "stm": Format.STM,
    "ctm": Format.CTM,
    "txt": Format.TXT,
}

REPORT_BY_NAME = {
    "sys": ReportType.SYS,
    "raw": ReportType.RAW,
    "pra": ReportType.PRA,
    "prf": ReportType.PRF,
    "sgml": ReportType.SGML,
}

EVAL_LABELS = {
    0x01: "correct",
    0x02: "substitution",
    0x04: "insertion",
    0x08: "deletion",
    0x10: "merge",
    0x20: "split",
}


@dataclass(frozen=True, slots=True)
class ScliteRecord:
    sequence: int
    group_index: int
    utterance_index: int
    group_name: str
    utterance: ScliteUtterance
    tokens: tuple[ScliteToken, ...]
    counts: ScliteCounts
    cumulative: ScliteCounts
