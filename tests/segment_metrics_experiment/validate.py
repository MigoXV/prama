from concurrent.futures import ThreadPoolExecutor
from itertools import product
import unittest
import numpy as np
from experiment import original, variants


class SegmentExperimentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backends = variants()

    def compare(self, reference, prediction, threshold):
        expected = original.evaluate_masks(reference, prediction, hit_threshold=threshold)
        for name, (evaluate, *_rest) in self.backends.items():
            with self.subTest(backend=name, threshold=threshold):
                self.assertEqual(evaluate(reference, prediction, hit_threshold=threshold), expected)

    def test_exhaustive_short_masks(self):
        masks = [np.array(bits, dtype=bool) for bits in product((False, True), repeat=5)]
        for reference in masks:
            for prediction in masks:
                for threshold in (0.0, np.nextafter(0.0, 1.0), 0.5, 0.9, 1.0):
                    self.compare(reference, prediction, threshold)

    def test_seeded_random_and_noncontiguous(self):
        rng = np.random.default_rng(20260926)
        for _ in range(300):
            size = int(rng.integers(4, 400))
            reference, prediction = rng.random((2, size)) > rng.random()
            self.compare(reference, prediction, float(rng.random()))
            self.compare(reference[::-2], prediction[::-2], 0.9)
            self.compare(reference.reshape(1, -1), prediction.reshape(-1, 1), 0.5)

    def test_threshold_rounding_boundary(self):
        reference = np.array([True] * 10 + [False], bool)
        prediction = np.array([True] * 9 + [False] * 2, bool)
        for threshold in (np.nextafter(0.9, 0), 0.9, np.nextafter(0.9, 1)):
            self.compare(reference, prediction, threshold)

    def test_validation_matches_original(self):
        for reference, prediction, threshold in (
            (np.array([], bool), np.array([], bool), 0.9),
            (np.ones(4), np.ones(4, bool), 0.9),
            (np.ones(4, bool), np.ones(3, bool), 0.9),
            (np.ones((2, 2), bool), np.ones((2, 2), bool), 0.9),
            (np.ones(1, bool), np.ones(1, bool), 0.9),
            (np.ones(4, bool), np.ones(4, bool), float('nan')),
            (np.ones(4, bool), np.ones(4, bool), -0.1),
            (np.ones(4, bool), np.ones(4, bool), 1.1),
        ):
            with self.assertRaises((TypeError, ValueError)) as caught:
                original.evaluate_masks(reference, prediction, hit_threshold=threshold)
            for evaluate, *_ in self.backends.values():
                with self.assertRaises(type(caught.exception)) as actual:
                    evaluate(reference, prediction, hit_threshold=threshold)
                self.assertEqual(str(actual.exception), str(caught.exception))

    def test_threads_and_no_mutation(self):
        rng = np.random.default_rng(9)
        reference, prediction = rng.random((2, 2000)) > 0.95
        saved = reference.copy(), prediction.copy()
        reference.flags.writeable = prediction.flags.writeable = False
        expected = original.evaluate_masks(reference, prediction)
        with ThreadPoolExecutor(max_workers=8) as pool:
            for name in ('scipy_c', 'numpy_c'):
                evaluate = self.backends[name][0]
                actual = list(pool.map(lambda _: evaluate(reference, prediction), range(200)))
                self.assertTrue(all(result == expected for result in actual))
        np.testing.assert_array_equal(reference, saved[0])
        np.testing.assert_array_equal(prediction, saved[1])


if __name__ == '__main__':
    unittest.main()
