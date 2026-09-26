from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from itertools import product

import numpy as np
import pytest

from prama.evaluator import VadEvaluator, evaluate_masks
from prama.models import VadEvaluationResult
from tests.test_vad.reference import evaluate_masks as reference_evaluate


@pytest.mark.parametrize('threshold', [0.0, np.nextafter(0.0, 1.0), 0.5, 0.9, 1.0])
def test_exhaustive_masks_match_original_formulas(threshold):
    masks = [np.array(bits, dtype=bool) for bits in product((False, True), repeat=5)]
    for ref in masks:
        for hyp in masks:
            assert evaluate_masks(ref, hyp, hit_threshold=threshold) == reference_evaluate(
                ref, hyp, hit_threshold=threshold
            )


def test_random_masks_and_strided_views():
    rng = np.random.default_rng(20260926)
    for _ in range(300):
        ref, hyp = rng.random((2, int(rng.integers(4, 400)))) > rng.random()
        threshold = float(rng.random())
        for left, right in ((ref, hyp), (ref[::-2], hyp[::-2]),
                            (ref[None, :], hyp[:, None])):
            assert evaluate_masks(left, right, hit_threshold=threshold) == reference_evaluate(
                left, right, hit_threshold=threshold
            )


def test_single_target_coverage_is_not_sum_of_overlaps():
    ref = np.ones(10, dtype=bool)
    hyp = np.array([True] * 4 + [False] * 2 + [True] * 4)
    result = evaluate_masks(ref, hyp, hit_threshold=0.7)
    assert result.segment_hit_count == 0
    assert result.segment_miss_count == 1
    assert result.segment_precision == 1.0
    assert result.segment_recall == 0.0


def test_touching_intervals_and_zero_threshold():
    ref = np.array([True, True, False, False])
    hyp = ~ref
    assert evaluate_masks(ref, hyp).segment_hit_count == 0
    assert evaluate_masks(ref, hyp).segment_false_alarm_count == 1
    assert evaluate_masks(ref, hyp, hit_threshold=0).segment_hit_count == 1
    assert evaluate_masks(ref, np.zeros_like(ref), hit_threshold=0).segment_hit_count == 0


@pytest.mark.parametrize('threshold', [np.nextafter(0.9, 0), 0.9, np.nextafter(0.9, 1)])
def test_floating_point_threshold_boundary(threshold):
    ref = np.array([True] * 10 + [False])
    hyp = np.array([True] * 9 + [False] * 2)
    result = evaluate_masks(ref, hyp, hit_threshold=threshold)
    assert result == reference_evaluate(ref, hyp, hit_threshold=threshold)
    assert result.segment_hit_count == int(threshold <= 0.9)


@pytest.mark.parametrize('ref,hyp,threshold', [
    (np.array([], bool), np.array([], bool), 0.9),
    (np.ones(1, bool), np.ones(1, bool), 0.9),
    (np.ones(4), np.ones(4, bool), 0.9),
    (np.ones(4, bool), np.ones(3, bool), 0.9),
    (np.ones((2, 2), bool), np.ones((2, 2), bool), 0.9),
    (np.ones(4, bool), np.ones(4, bool), float('nan')),
    (np.ones(4, bool), np.ones(4, bool), -0.1),
    (np.ones(4, bool), np.ones(4, bool), 1.1),
])
def test_original_validation_errors(ref, hyp, threshold):
    with pytest.raises((TypeError, ValueError)) as expected:
        reference_evaluate(ref, hyp, hit_threshold=threshold)
    with pytest.raises(type(expected.value)) as actual:
        evaluate_masks(ref, hyp, hit_threshold=threshold)
    assert str(actual.value) == str(expected.value)


def test_shared_evaluator_with_read_only_arrays_across_threads():
    rng = np.random.default_rng(14)
    ref, hyp = rng.random((2, 4096)) > 0.95
    saved = ref.copy(), hyp.copy()
    ref.flags.writeable = hyp.flags.writeable = False
    evaluator = VadEvaluator(hit_threshold=0.5)
    expected = reference_evaluate(ref, hyp, hit_threshold=0.5)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: evaluator.evaluate(ref, hyp), range(200)))
    assert all(item == expected for item in results)
    assert isinstance(results[0], VadEvaluationResult)
    assert type(asdict(results[0])['segment_hit_count']) is int
    np.testing.assert_array_equal(ref, saved[0])
    np.testing.assert_array_equal(hyp, saved[1])


def test_many_fragments_without_quadratic_work():
    # 50k disjoint segments on each side: an R x P matrix would need GBs.
    ref = np.arange(100_000) % 2 == 0
    result = evaluate_masks(ref, ref)
    assert result.reference_segment_count == 50_000
    assert result.segment_hit_count == 50_000
    assert result.segment_f1 == 1.0
