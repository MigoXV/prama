from __future__ import annotations

from dataclasses import dataclass
from typing import List

from prama.sclite import ScliteCounts, ScliteGroup


@dataclass(frozen=True, slots=True)
class WerToken:
    eval: int
    eval_label: str
    ref_word: str | None
    hyp_word: str | None


@dataclass(frozen=True, slots=True)
class WerUtterance:
    id: str
    tokens: List[WerToken]


@dataclass(frozen=True, slots=True)
class WerResult:
    summary: ScliteCounts
    groups: List[ScliteGroup]
    utterances: List[WerUtterance]
    report: str
    metric: str = "wer"

    @property
    def wer(self) -> float:
        return self.summary.wer

    @property
    def cer(self) -> float:
        return self.summary.wer

    @property
    def accuracy(self) -> float:
        return self.summary.accuracy
