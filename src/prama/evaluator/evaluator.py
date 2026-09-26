from __future__ import annotations

from itertools import zip_longest
from pathlib import Path
from types import TracebackType
from typing import List, Optional

from prama.models import WerRecord, WerResult, WerToken, WerUtterance
from prama.sclite import (
    Format,
    IdType,
    ReportType,
    ScliteClient,
    ScliteOptions,
    ScliteResult,
    ScliteStream,
)


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
            return _convert_result(result, metric)

    def iter_wer(
        self,
        references: list[str],
        hypotheses: list[str],
        utterance_ids: list[str] | None = None,
    ) -> EvaluationStream:
        return self._iter_evaluate(references, hypotheses, utterance_ids, "wer", 0)

    def iter_cer(
        self,
        references: list[str],
        hypotheses: list[str],
        utterance_ids: list[str] | None = None,
    ) -> EvaluationStream:
        return self._iter_evaluate(
            references, hypotheses, utterance_ids, "cer", CALI_ON
        )

    def _iter_evaluate(self, references, hypotheses, utterance_ids, metric, flags):
        self._ensure_open()
        ref, hyp = _texts_to_trn(references, hypotheses, utterance_ids)
        stream = self._client.iter_align_texts(
            ref,
            hyp,
            ref_format=Format.TRN,
            hyp_format=Format.TRN,
            options=ScliteOptions(
                id_type=IdType.SP, encoding="UTF-8", char_align_flags=flags
            ),
        )
        return EvaluationStream(stream, metric)

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

    for index, (ref_line, hyp_line) in enumerate(
        zip_longest(references, hypotheses, fillvalue="")
    ):
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
        raise ValueError(
            "utterance_ids length must match the number of evaluated pairs"
        )
    for utterance_id in utterance_ids:
        if not utterance_id.strip():
            raise ValueError("utterance_ids must not contain empty ids")
        if any(char in utterance_id for char in "()\r\n"):
            raise ValueError("utterance_ids must not contain parentheses or newlines")
    return utterance_ids


def _to_trn_line(text: str, utterance_id: str) -> str:
    clean_text = " ".join(text.split())
    return f"{clean_text} ({utterance_id})" if clean_text else f"({utterance_id})"


def _convert_result(result: ScliteResult, metric: str) -> WerResult:
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


class EvaluationStream:
    def __init__(
        self, stream: ScliteStream, metric: str, owner: Evaluator | None = None
    ) -> None:
        self._stream = stream
        self._metric = metric
        self._owner = owner
        self._result = None

    def __enter__(self) -> EvaluationStream:
        self._stream.__enter__()
        return self

    def __exit__(self, *_):
        self.close()

    def __iter__(self) -> EvaluationStream:
        return self

    def __next__(self) -> WerRecord:
        event = next(self._stream)
        utterance = WerUtterance(
            event.utterance.id,
            [
                WerToken(t.eval, t.eval_label, t.ref_word, t.hyp_word)
                for t in event.tokens
            ],
        )
        return WerRecord(
            event.sequence,
            event.group_index,
            event.utterance_index,
            event.group_name,
            utterance,
            event.counts,
            event.cumulative,
            self._metric,
        )

    def result(self) -> WerResult:
        if self._result is None:
            self._result = _convert_result(self._stream.result(), self._metric)
        return self._result

    def close(self) -> None:
        self._stream.close()
        if self._owner is not None:
            self._owner.close()
            self._owner = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def iter_wer(
    references: list[str], hypotheses: list[str], utterance_ids: list[str] | None = None
) -> EvaluationStream:
    evaluator = Evaluator()
    try:
        stream = evaluator.iter_wer(references, hypotheses, utterance_ids)
        stream._owner = evaluator
        return stream
    except BaseException:
        evaluator.close()
        raise


def iter_cer(
    references: list[str], hypotheses: list[str], utterance_ids: list[str] | None = None
) -> EvaluationStream:
    evaluator = Evaluator()
    try:
        stream = evaluator.iter_cer(references, hypotheses, utterance_ids)
        stream._owner = evaluator
        return stream
    except BaseException:
        evaluator.close()
        raise
