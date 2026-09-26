from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from prama.models.vad import VadEvaluationResult

Segments = NDArray[np.intp]


class VadEvaluator:
    """Evaluate boolean VAD masks with NumPy; instances hold only the threshold."""

    def __init__(self, hit_threshold: float = 0.9) -> None:
        self.hit_threshold = hit_threshold

    def evaluate(
        self,
        reference_mask: NDArray[np.bool_],
        prediction_mask: NDArray[np.bool_],
    ) -> VadEvaluationResult:
        return evaluate_masks(
            reference_mask,
            prediction_mask,
            hit_threshold=self.hit_threshold,
        )


def evaluate_masks(
    reference_mask: NDArray[np.bool_],
    prediction_mask: NDArray[np.bool_],
    *,
    hit_threshold: float = 0.9,
) -> VadEvaluationResult:
    """Return frame/segment VAD metrics; ratios are fractions, not percentages.

    Preserve prama-server's per-reference single-target coverage semantics.
    Inputs are never modified; independent calls may run in multiple threads.
    """
    if not 0.0 <= hit_threshold <= 1.0:
        raise ValueError(f"hit_threshold 必须在 [0, 1] 内: {hit_threshold}")

    reference = _as_bool_mask(reference_mask, name="reference_mask")
    prediction = _as_bool_mask(prediction_mask, name="prediction_mask")
    if reference.shape != prediction.shape:
        raise ValueError(
            "reference_mask 与 prediction_mask 形状必须一致: "
            f"{reference.shape} != {prediction.shape}"
        )

    tp = int(np.count_nonzero(reference & prediction))
    tn = int(np.count_nonzero(~reference & ~prediction))
    fp = int(np.count_nonzero(~reference & prediction))
    fn = int(np.count_nonzero(reference & ~prediction))

    total = reference.size
    speech_frames = int(np.count_nonzero(reference))
    non_speech_frames = total - speech_frames
    frame_accuracy = (tp + tn) / total if total else 1.0
    frame_recall = _safe_divide(tp, tp + fn)
    frame_precision = _safe_divide(tp, tp + fp)
    frame_f1 = _f1(frame_precision, frame_recall)
    frame_specificity = _safe_divide(tn, tn + fp)
    frame_false_alarm_rate = _safe_divide(fp, fp + tn)
    frame_miss_rate = _safe_divide(fn, fn + tp)
    frame_balanced_accuracy = (frame_recall + frame_specificity) / 2

    reference_segments = _connected_segments(reference)
    prediction_segments = _connected_segments(prediction)
    segment_hit_count = _segment_hit_count(
        source_segments=reference_segments,
        target_segments=prediction_segments,
        hit_threshold=hit_threshold,
    )
    prediction_hit_count = _segment_overlap_count(
        source_segments=prediction_segments,
        target_segments=reference_segments,
    )
    segment_false_alarm_count = len(prediction_segments) - prediction_hit_count
    segment_miss_count = len(reference_segments) - segment_hit_count
    segment_recall = _safe_divide(segment_hit_count, len(reference_segments))
    segment_precision = _safe_divide(prediction_hit_count, len(prediction_segments))
    segment_f1 = _f1(segment_precision, segment_recall)
    segment_miss_rate = _safe_divide(segment_miss_count, len(reference_segments))
    segment_false_alarm_rate = _safe_divide(
        segment_false_alarm_count,
        len(prediction_segments),
    )

    return VadEvaluationResult(
        frame_total=total,
        frame_speech=speech_frames,
        frame_non_speech=non_speech_frames,
        frame_true_positive=tp,
        frame_true_negative=tn,
        frame_false_positive=fp,
        frame_false_negative=fn,
        frame_accuracy=frame_accuracy,
        frame_recall=frame_recall,
        frame_precision=frame_precision,
        frame_f1=frame_f1,
        frame_specificity=frame_specificity,
        frame_false_alarm_rate=frame_false_alarm_rate,
        frame_miss_rate=frame_miss_rate,
        frame_balanced_accuracy=frame_balanced_accuracy,
        segment_hit_count=segment_hit_count,
        segment_miss_count=segment_miss_count,
        segment_false_alarm_count=segment_false_alarm_count,
        segment_recall=segment_recall,
        segment_precision=segment_precision,
        segment_f1=segment_f1,
        segment_miss_rate=segment_miss_rate,
        segment_false_alarm_rate=segment_false_alarm_rate,
        reference_segment_count=len(reference_segments),
        prediction_segment_count=len(prediction_segments),
    )


def _as_bool_mask(mask: NDArray[np.bool_], *, name: str) -> NDArray[np.bool_]:
    array = np.asarray(mask)
    if array.dtype != np.bool_:
        raise TypeError(f"{name} 必须是 bool np.ndarray: dtype={array.dtype}")
    array = np.squeeze(array)
    if array.ndim != 1:
        raise ValueError(f"{name} 必须是一维 bool mask: shape={array.shape}")
    return array


def _connected_segments(mask: NDArray[np.bool_]) -> Segments:
    if mask.size == 0:
        # Preserve the original SciPy find_objects exception for empty masks.
        raise ValueError(
            "zero-size array to reduction operation maximum which has no identity"
        )
    padded = np.empty(mask.size + 2, dtype=np.bool_)
    padded[0] = padded[-1] = False
    padded[1:-1] = mask
    return np.flatnonzero(padded[1:] != padded[:-1]).reshape(-1, 2)


def _overlap_candidates(
    source: Segments, target: Segments,
) -> tuple[NDArray[np.intp], NDArray[np.intp]]:
    # Both sides are sorted, disjoint, positive-length half-open intervals.
    first = np.searchsorted(target[:, 1], source[:, 0], side="right")
    stop = np.searchsorted(target[:, 0], source[:, 1], side="left")
    return first, stop - first


def _segment_hit_count(
    *,
    source_segments: Segments,
    target_segments: Segments,
    hit_threshold: float,
) -> int:
    source, target = source_segments, target_segments
    if not len(source) or not len(target):
        return 0
    # The original any(overlap / length >= 0) includes disjoint targets.
    if hit_threshold == 0.0:
        return len(source)
    first, lengths = _overlap_candidates(source, target)
    source_index = np.repeat(np.arange(len(source)), lengths)
    offsets = np.cumsum(lengths) - lengths
    target_index = np.arange(len(source_index)) + np.repeat(first - offsets, lengths)
    overlap = (
        np.minimum(source[source_index, 1], target[target_index, 1])
        - np.maximum(source[source_index, 0], target[target_index, 0])
    )
    # Only enumerate actual overlaps, avoiding an R x P allocation.
    maximum = np.zeros(len(source), dtype=np.intp)
    np.maximum.at(maximum, source_index, overlap)
    return int(np.count_nonzero(maximum / (source[:, 1] - source[:, 0]) >= hit_threshold))


def _segment_overlap_count(
    *, source_segments: Segments, target_segments: Segments,
) -> int:
    if not len(source_segments) or not len(target_segments):
        return 0
    _, lengths = _overlap_candidates(source_segments, target_segments)
    return int(np.count_nonzero(lengths))


def _safe_divide(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)
