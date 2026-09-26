"""独立实验：仅替换原函数私有副本的 globals，不修改服务器模块。"""
from __future__ import annotations

import ctypes
import hashlib
import importlib
import os
from pathlib import Path
import subprocess
from types import FunctionType

import numpy as np

ROOT = Path(__file__).resolve().parent
original = importlib.import_module("prama_server.evaluator.vad.evaluator")


def build_native() -> Path:
    source = ROOT / "segments.c"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    library = ROOT / f"segments-{digest}.so"
    if not library.exists():
        temporary = library.with_suffix(f".{os.getpid()}.so")
        subprocess.run(["cc", "-std=c11", "-O3", "-Wall", "-Wextra", "-Werror",
                        "-shared", "-fPIC", str(source), "-o", str(temporary)], check=True)
        temporary.replace(library)
    return library


class Native:
    def __init__(self):
        self.lib = ctypes.CDLL(str(build_native()))  # CDLL releases the GIL.
        array = np.ctypeslib.ndpointer(dtype=np.intp, ndim=2,
                                     flags=("C_CONTIGUOUS", "ALIGNED"))
        self.lib.segment_hits.argtypes = [array, ctypes.c_ssize_t, array,
                                         ctypes.c_ssize_t, ctypes.c_double, ctypes.c_int]
        self.lib.segment_hits.restype = ctypes.c_ssize_t

    def hits(self, *, source_segments, target_segments, hit_threshold=0.0,
             positive_overlap=False):
        # Private kernel accepts only sorted, disjoint (start, stop) arrays
        # created below. No copy for already contiguous np.intp arrays.
        source = np.ascontiguousarray(source_segments, dtype=np.intp).reshape(-1, 2)
        target = np.ascontiguousarray(target_segments, dtype=np.intp).reshape(-1, 2)
        return int(self.lib.segment_hits(source, len(source), target, len(target),
                                        hit_threshold, positive_overlap))

    def overlaps(self, **kwargs):
        return self.hits(**kwargs, positive_overlap=True)


def scipy_segments(mask):
    return np.asarray(original._connected_segments(mask), dtype=np.intp).reshape(-1, 2)


def numpy_segments(mask):
    # Keep the current SciPy empty-input exception for exact compatibility.
    if mask.size == 0:
        return scipy_segments(mask)
    # Boundary detection also accepts strided and reversed masks.
    padded = np.empty(mask.size + 2, dtype=np.bool_)
    padded[0] = padded[-1] = False
    padded[1:-1] = mask
    return np.flatnonzero(padded[1:] != padded[:-1]).reshape(-1, 2)


def numpy_hits(*, source_segments, target_segments, hit_threshold=0.0,
               positive_overlap=False):
    source = np.asarray(source_segments, dtype=np.intp).reshape(-1, 2)
    target = np.asarray(target_segments, dtype=np.intp).reshape(-1, 2)
    if not len(source) or not len(target):
        return 0
    if not positive_overlap and hit_threshold == 0.0:
        return len(source)
    first = np.searchsorted(target[:, 1], source[:, 0], side="right")
    stop = np.searchsorted(target[:, 0], source[:, 1], side="left")
    lengths = stop - first
    if positive_overlap:
        return int(np.count_nonzero(lengths))
    # Enumerate only overlapping pairs, never materialize an S x T matrix.
    source_index = np.repeat(np.arange(len(source)), lengths)
    offsets = np.cumsum(lengths) - lengths
    target_index = (np.arange(len(source_index))
                    + np.repeat(first - offsets, lengths))
    overlap = (np.minimum(source[source_index, 1], target[target_index, 1])
               - np.maximum(source[source_index, 0], target[target_index, 0]))
    maximum = np.zeros(len(source), dtype=np.intp)
    np.maximum.at(maximum, source_index, overlap)
    return int(np.count_nonzero(maximum / (source[:, 1] - source[:, 0]) >= hit_threshold))


def numpy_overlaps(**kwargs):
    return numpy_hits(**kwargs, positive_overlap=True)


def python_hits(*, source_segments, target_segments, hit_threshold=0.0,
                positive_overlap=False):
    # Same interval sweep as C, to separate algorithm and language effects.
    count, first = 0, 0
    for start, end in source_segments:
        if not positive_overlap and hit_threshold == 0.0 and len(target_segments):
            count += 1
            continue
        while first < len(target_segments) and target_segments[first][1] <= start:
            first += 1
        for j in range(first, len(target_segments)):
            left, right = target_segments[j]
            if left >= end:
                break
            overlap = max(0, min(end, right) - max(start, left))
            if (overlap > 0 if positive_overlap else overlap / (end-start) >= hit_threshold):
                count += 1
                break
    return count


def python_overlaps(**kwargs):
    return python_hits(**kwargs, positive_overlap=True)


def clone_evaluator(extract, hits, overlaps):
    """Keep all original validation/frame metrics/formulas and repeated work."""
    namespace = dict(original.evaluate_masks.__globals__)
    namespace.update(_connected_segments=extract, _segment_hit_count=hits,
                     _segment_overlap_count=overlaps)
    # ndarray requires len(), not list truthiness; retain original repeat call.
    def score(*, source_segments, target_segments, hit_threshold):
        if not len(source_segments):
            return 0.0
        return hits(source_segments=source_segments, target_segments=target_segments,
                    hit_threshold=hit_threshold) / len(source_segments)
    namespace["_segment_score"] = score
    function = original.evaluate_masks
    result = FunctionType(function.__code__, namespace, function.__name__,
                          function.__defaults__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def variants():
    native = Native()
    return {
        "original": (original.evaluate_masks, original._connected_segments,
                     original._segment_hit_count, original._segment_overlap_count),
        "python_sweep": (clone_evaluator(original._connected_segments, python_hits, python_overlaps),
                         original._connected_segments, python_hits, python_overlaps),
        "numpy": (clone_evaluator(numpy_segments, numpy_hits, numpy_overlaps),
                  numpy_segments, numpy_hits, numpy_overlaps),
        "scipy_c": (clone_evaluator(scipy_segments, native.hits, native.overlaps),
                    scipy_segments, native.hits, native.overlaps),
        "numpy_c": (clone_evaluator(numpy_segments, native.hits, native.overlaps),
                    numpy_segments, native.hits, native.overlaps),
    }
