from __future__ import annotations

import ctypes
import os
from pathlib import Path

from prama._sclite_native import (
    CCounts,
    COptions,
    CToken,
    CUtterance,
    find_sclite_library,
    load_sclite_library,
)
from prama._sclite_types import (
    EVAL_LABELS,
    FORMAT_BY_NAME,
    REPORT_BY_NAME,
    Format,
    ReportType,
    ScliteCounts,
    ScliteError,
    ScliteGroup,
    ScliteOptions,
    ScliteToken,
    ScliteUtterance,
)


def _decode(value: bytes | None) -> str:
    return "" if value is None else value.decode("utf-8", errors="replace")


def _decode_optional(value: bytes | None) -> str | None:
    return None if value is None else value.decode("utf-8", errors="replace")


def _to_bytes(value: str | bytes) -> bytes:
    return value if isinstance(value, bytes) else value.encode("utf-8")


def _path_to_bytes(value: str | Path | None) -> bytes | None:
    return None if value is None else os.fsencode(value)


def _string_to_bytes(value: str | None) -> bytes | None:
    return None if value is None else value.encode("utf-8")


def _coerce_format(value: Format | str | int) -> Format:
    if isinstance(value, Format):
        return value
    if isinstance(value, str):
        try:
            return FORMAT_BY_NAME[value.lower()]
        except KeyError as exc:
            raise ValueError(f"unsupported sclite format: {value}") from exc
    return Format(value)


def _coerce_report_type(value: ReportType | str | int) -> ReportType:
    if isinstance(value, ReportType):
        return value
    if isinstance(value, str):
        try:
            return REPORT_BY_NAME[value.lower()]
        except KeyError as exc:
            raise ValueError(f"unsupported sclite report type: {value}") from exc
    return ReportType(value)


def _coerce_counts(counts: CCounts) -> ScliteCounts:
    return ScliteCounts(
        ref_words=counts.ref_words,
        hyp_words=counts.hyp_words,
        correct=counts.correct,
        substitutions=counts.substitutions,
        deletions=counts.deletions,
        insertions=counts.insertions,
        sentence_count=counts.sentence_count,
        sentence_errors=counts.sentence_errors,
        wer=counts.wer,
        accuracy=counts.accuracy,
    )


class ScliteClient:
    def __init__(self, lib_path: str | Path | None = None) -> None:
        self._lib, resolved_path = load_sclite_library(lib_path)
        self.lib_path = Path(resolved_path) if isinstance(resolved_path, Path) else resolved_path
        self._ctx = self._lib.sclite_context_new()
        if not self._ctx:
            raise ScliteError("failed to create sclite context")

    def close(self) -> None:
        if getattr(self, "_ctx", None):
            self._lib.sclite_context_free(self._ctx)
            self._ctx = None

    def __enter__(self) -> ScliteClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def align_texts(
        self,
        ref_data: str | bytes,
        hyp_data: str | bytes,
        *,
        ref_format: Format | str | int,
        hyp_format: Format | str | int,
        options: ScliteOptions | None = None,
    ) -> ScliteResult:
        self._ensure_open()
        ref_bytes = _to_bytes(ref_data)
        hyp_bytes = _to_bytes(hyp_data)
        c_options, keepalive = self._build_options(options)
        result = ctypes.c_void_p()
        rc = self._lib.sclite_align_texts(
            self._ctx,
            ref_bytes,
            len(ref_bytes),
            int(_coerce_format(ref_format)),
            hyp_bytes,
            len(hyp_bytes),
            int(_coerce_format(hyp_format)),
            ctypes.byref(c_options),
            ctypes.byref(result),
        )
        if rc != 0:
            raise ScliteError(self._context_error())
        return ScliteResult(self._lib, self._ctx, result, keepalive)

    def align_files(
        self,
        ref_path: str | Path,
        hyp_path: str | Path,
        *,
        ref_format: Format | str | int,
        hyp_format: Format | str | int,
        options: ScliteOptions | None = None,
    ) -> ScliteResult:
        return self.align_texts(
            Path(ref_path).read_bytes(),
            Path(hyp_path).read_bytes(),
            ref_format=ref_format,
            hyp_format=hyp_format,
            options=options,
        )

    def _build_options(self, options: ScliteOptions | None) -> tuple[COptions, list[bytes]]:
        c_options = COptions()
        self._lib.sclite_options_init(ctypes.byref(c_options))
        if options is None:
            return c_options, []

        title, encoding, language_profile, lexicon_path, wwl_path, lm_path = (
            _string_to_bytes(options.title),
            _string_to_bytes(options.encoding),
            _string_to_bytes(options.language_profile),
            _path_to_bytes(options.lexicon_path),
            _path_to_bytes(options.wwl_path),
            _path_to_bytes(options.lm_path),
        )
        keepalive = [
            value
            for value in (title, encoding, language_profile, lexicon_path, wwl_path, lm_path)
            if value is not None
        ]
        c_options.title = title
        c_options.id_type = int(options.id_type)
        c_options.encoding = encoding
        c_options.language_profile = language_profile
        c_options.case_sensitive = int(options.case_sensitive)
        c_options.char_align_flags = options.char_align_flags
        c_options.fragment_correct = int(options.fragment_correct)
        c_options.optional_deletion = int(options.optional_deletion)
        c_options.time_align = int(options.time_align)
        c_options.left_to_right = int(options.left_to_right)
        c_options.infer_word_seg = int(options.infer_word_seg)
        c_options.lexicon_path = lexicon_path
        c_options.infer_flags = options.infer_flags
        c_options.reduce_ref_segments = int(options.reduce_ref_segments)
        c_options.reduce_hyp_words = int(options.reduce_hyp_words)
        c_options.wwl_path = wwl_path
        c_options.lm_path = lm_path
        c_options.feedback = options.feedback
        return c_options, keepalive

    def _context_error(self) -> str:
        return _decode(self._lib.sclite_context_error(self._ctx)) or "sclite failed"

    def _ensure_open(self) -> None:
        if not getattr(self, "_ctx", None):
            raise ScliteError("sclite client is closed")


class ScliteResult:
    def __init__(
        self,
        lib: ctypes.CDLL,
        ctx: int,
        result: ctypes.c_void_p,
        keepalive: list[bytes],
    ) -> None:
        self._lib = lib
        self._ctx = ctx
        self._result = result
        self._keepalive = keepalive

    def close(self) -> None:
        if self._result:
            self._lib.sclite_result_free(self._result)
            self._result = None

    def __enter__(self) -> ScliteResult:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def summary(self) -> ScliteCounts:
        self._ensure_open()
        counts = CCounts()
        if self._lib.sclite_result_summary(self._result, ctypes.byref(counts)) != 0:
            raise ScliteError("failed to read sclite summary")
        return _coerce_counts(counts)

    def groups(self) -> list[ScliteGroup]:
        self._ensure_open()
        count = self._lib.sclite_result_group_count(self._result)
        if count < 0:
            raise ScliteError("failed to read sclite group count")
        groups: list[ScliteGroup] = []
        for group_index in range(count):
            name = ctypes.c_char_p()
            counts = CCounts()
            rc = self._lib.sclite_result_group_summary(
                self._result,
                group_index,
                ctypes.byref(name),
                ctypes.byref(counts),
            )
            if rc != 0:
                raise ScliteError(f"failed to read sclite group {group_index}")
            groups.append(ScliteGroup(name=_decode(name.value), counts=_coerce_counts(counts)))
        return groups

    def utterances(self, group_index: int = 0) -> list[ScliteUtterance]:
        self._ensure_open()
        count = self._lib.sclite_result_utterance_count(self._result, group_index)
        if count < 0:
            raise ScliteError(f"failed to read utterance count for group {group_index}")
        utterances: list[ScliteUtterance] = []
        for utterance_index in range(count):
            utterance = CUtterance()
            rc = self._lib.sclite_result_utterance(
                self._result,
                group_index,
                utterance_index,
                ctypes.byref(utterance),
            )
            if rc != 0:
                raise ScliteError(f"failed to read utterance {utterance_index}")
            utterances.append(
                ScliteUtterance(
                    id=_decode(utterance.id),
                    labels=_decode(utterance.labels),
                    file=_decode(utterance.file),
                    channel=_decode(utterance.channel),
                    ref_start=utterance.ref_start,
                    ref_end=utterance.ref_end,
                    hyp_start=utterance.hyp_start,
                    hyp_end=utterance.hyp_end,
                    token_count=utterance.token_count,
                )
            )
        return utterances

    def tokens(self, group_index: int = 0, utterance_index: int = 0) -> list[ScliteToken]:
        utterances = self.utterances(group_index)
        if utterance_index < 0 or utterance_index >= len(utterances):
            raise ScliteError(f"utterance index out of range: {utterance_index}")
        token_count = utterances[utterance_index].token_count
        tokens: list[ScliteToken] = []
        for token_index in range(token_count):
            token = CToken()
            rc = self._lib.sclite_result_token(
                self._result,
                group_index,
                utterance_index,
                token_index,
                ctypes.byref(token),
            )
            if rc != 0:
                raise ScliteError(f"failed to read token {token_index}")
            tokens.append(
                ScliteToken(
                    eval=token.eval,
                    eval_label=EVAL_LABELS.get(token.eval, f"unknown:{token.eval}"),
                    ref_word=_decode_optional(token.ref_word),
                    hyp_word=_decode_optional(token.hyp_word),
                    ref_start=token.ref_start,
                    ref_end=token.ref_end,
                    hyp_start=token.hyp_start,
                    hyp_end=token.hyp_end,
                    ref_conf=token.ref_conf,
                    hyp_conf=token.hyp_conf,
                    ref_weight=token.ref_weight,
                    hyp_weight=token.hyp_weight,
                )
            )
        return tokens

    def report_text(self, report_type: ReportType | str | int = ReportType.PRA) -> str:
        self._ensure_open()
        out_data = ctypes.c_void_p()
        out_len = ctypes.c_size_t()
        rc = self._lib.sclite_result_report_text(
            self._ctx,
            self._result,
            int(_coerce_report_type(report_type)),
            ctypes.byref(out_data),
            ctypes.byref(out_len),
        )
        if rc != 0:
            raise ScliteError("failed to generate sclite report")
        try:
            data = ctypes.string_at(out_data, out_len.value)
            return data.decode("utf-8", errors="replace")
        finally:
            self._lib.sclite_free_string(out_data)

    def _ensure_open(self) -> None:
        if not self._result:
            raise ScliteError("sclite result is closed")


__all__ = ["ScliteClient", "ScliteResult", "find_sclite_library"]
