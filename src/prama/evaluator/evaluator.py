from __future__ import annotations

from itertools import zip_longest
from pathlib import Path
from types import TracebackType
from typing import List, Optional

from prama.models import WerResult, WerToken, WerUtterance
from prama.sclite import Format, IdType, ReportType, ScliteClient, ScliteOptions


CALI_ON = 1


class Evaluator:
    def __init__(self, lib_path: str | Path | None = None) -> None:
        self.lib_path = lib_path
        self._client: ScliteClient | None = ScliteClient(lib_path=lib_path)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> Evaluator:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def get_wer(
        self,
        references: List[str],
        hypotheses: List[str],
        utterance_ids: Optional[List[str]] = None,
    ) -> WerResult:
        return self._evaluate(
            references,
            hypotheses,
            utterance_ids=utterance_ids,
            metric="wer",
            char_align_flags=0,
        )

    def get_cer(
        self,
        references: List[str],
        hypotheses: List[str],
        utterance_ids: Optional[List[str]] = None,
    ) -> WerResult:
        return self._evaluate(
            references,
            hypotheses,
            utterance_ids=utterance_ids,
            metric="cer",
            char_align_flags=CALI_ON,
        )

    def _evaluate(
        self,
        references: List[str],
        hypotheses: List[str],
        *,
        utterance_ids: Optional[List[str]],
        metric: str,
        char_align_flags: int,
    ) -> WerResult:
        ref_trn, hyp_trn = _texts_to_trn(references, hypotheses, utterance_ids)
        options = ScliteOptions(
            id_type=IdType.SP,
            encoding="UTF-8",
            char_align_flags=char_align_flags,
        )

        self._ensure_open()
        with self._client.align_texts(
            ref_trn,
            hyp_trn,
            ref_format=Format.TRN,
            hyp_format=Format.TRN,
            options=options,
        ) as result:
            groups = result.groups()
            utterances = [
                WerUtterance(
                    id=utterance.id,
                    tokens=[
                        WerToken(
                            eval=token.eval,
                            eval_label=token.eval_label,
                            ref_word=token.ref_word,
                            hyp_word=token.hyp_word,
                        )
                        for token in result.tokens(group_index, utterance_index)
                    ],
                )
                for group_index in range(len(groups))
                for utterance_index, utterance in enumerate(result.utterances(group_index))
            ]
            return WerResult(
                summary=result.summary(),
                groups=groups,
                utterances=utterances,
                report=result.report_text(ReportType.PRA),
                metric=metric,
            )

    def _ensure_open(self) -> None:
        if self._client is None:
            raise RuntimeError("evaluator is closed")


def get_wer(
    references: List[str],
    hypotheses: List[str],
    utterance_ids: Optional[List[str]] = None,
) -> WerResult:
    with Evaluator() as evaluator:
        return evaluator.get_wer(references, hypotheses, utterance_ids)


def get_cer(
    references: List[str],
    hypotheses: List[str],
    utterance_ids: Optional[List[str]] = None,
) -> WerResult:
    with Evaluator() as evaluator:
        return evaluator.get_cer(references, hypotheses, utterance_ids)


def _texts_to_trn(
    references: List[str],
    hypotheses: List[str],
    utterance_ids: Optional[List[str]],
) -> tuple[str, str]:
    _validate_texts(references, "references")
    _validate_texts(hypotheses, "hypotheses")
    if not references and not hypotheses:
        raise ValueError("references and hypotheses must not both be empty")

    pair_count = max(len(references), len(hypotheses))
    ids = _resolve_utterance_ids(utterance_ids, pair_count)
    ref_trn: List[str] = []
    hyp_trn: List[str] = []

    for index, (ref_line, hyp_line) in enumerate(zip_longest(references, hypotheses, fillvalue="")):
        utterance_id = ids[index]
        ref_trn.append(_to_trn_line(ref_line, utterance_id))
        hyp_trn.append(_to_trn_line(hyp_line, utterance_id))

    return "\n".join(ref_trn) + "\n", "\n".join(hyp_trn) + "\n"


def _validate_texts(texts: List[str], name: str) -> None:
    if not isinstance(texts, list):
        raise TypeError(f"{name} must be a List[str]")
    if not all(isinstance(text, str) for text in texts):
        raise TypeError(f"{name} must be a List[str]")


def _resolve_utterance_ids(
    utterance_ids: Optional[List[str]],
    pair_count: int,
) -> List[str]:
    if utterance_ids is None:
        return [f"utt{index + 1:04d}" for index in range(pair_count)]
    _validate_texts(utterance_ids, "utterance_ids")
    if len(utterance_ids) != pair_count:
        raise ValueError("utterance_ids length must match the number of evaluated pairs")
    for utterance_id in utterance_ids:
        if not utterance_id.strip():
            raise ValueError("utterance_ids must not contain empty ids")
        if any(char in utterance_id for char in "()\r\n"):
            raise ValueError("utterance_ids must not contain parentheses or newlines")
    return utterance_ids


def _to_trn_line(text: str, utterance_id: str) -> str:
    clean_text = " ".join(text.split())
    return f"{clean_text} ({utterance_id})" if clean_text else f"({utterance_id})"
