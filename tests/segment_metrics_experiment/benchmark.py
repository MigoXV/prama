"""Run in the server Poetry environment; retain raw timing samples."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import platform
from pathlib import Path
import statistics
import subprocess
import time
import tracemalloc
import numpy as np
import scipy
from experiment import ROOT, original, variants


def cases():
    rng = np.random.default_rng(20260926)
    def speech(size, run):
        return np.logical_xor.accumulate(rng.random(size) < 1 / run)
    return {
        'silence': (np.zeros(60000, bool), np.zeros(60000, bool)),
        '30s_sparse': (speech(3000, 75), speech(3000, 75)),
        '10min_sparse': (speech(60000, 100), speech(60000, 100)),
        '1h_sparse': (speech(360000, 250), speech(360000, 250)),
        'fragmented': (np.arange(4096) % 2 == 0, np.arange(4096) % 3 == 0),
        'all_speech': (np.ones(60000, bool), np.ones(60000, bool)),
    }


def measure(fn, repeats):
    start = time.perf_counter_ns()
    fn()
    duration = max(1, time.perf_counter_ns() - start)
    batch = min(256, max(1, int(25_000_000 / duration)))
    samples = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        for _ in range(batch):
            fn()
        samples.append((time.perf_counter_ns() - start) / batch / 1e6)
    return {'median_ms': statistics.median(samples), 'samples_ms': samples, 'batch': batch}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--output', type=Path, default=ROOT / 'results.json')
    args = parser.parse_args()
    backends = variants()
    source = Path(original.__file__)
    output = {'environment': {
        'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__,
        'platform': platform.platform(), 'cpu_count': os.cpu_count(),
        'cpu': next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                     if line.startswith('model name')), 'unknown'),
        'compiler': subprocess.check_output(['cc', '--version'], text=True).splitlines()[0],
        'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'server_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source.parent, text=True).strip(),
        'seed': 20260926, 'repeats': args.repeats,
    }, 'cases': [], 'threads': []}
    for case, (ref, hyp) in cases().items():
        expected = original.evaluate_masks(ref, hyp)
        for name, (evaluate, extract, hits, overlaps) in backends.items():
            assert evaluate(ref, hyp) == expected, (case, name)
            refs, hyps = extract(ref), extract(hyp)
            def matching():
                a = hits(source_segments=refs, target_segments=hyps, hit_threshold=0.9)
                b = overlaps(source_segments=hyps, target_segments=refs)
                c = hits(source_segments=refs, target_segments=hyps, hit_threshold=0.9)
                return a, b, c
            item = {'case': case, 'backend': name, 'frames': len(ref),
                    'reference_segments': len(refs), 'prediction_segments': len(hyps),
                    'extract': measure(lambda: (extract(ref), extract(hyp)), args.repeats),
                    'match': measure(matching, args.repeats),
                    'evaluate': measure(lambda: evaluate(ref, hyp), args.repeats)}
            tracemalloc.start()
            evaluate(ref, hyp)
            item['traced_peak_bytes'] = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            output['cases'].append(item)
            print(case, name, f'{item["evaluate"]["median_ms"]:.4f} ms', flush=True)
        args.output.write_text(json.dumps(output, indent=2) + '\n')
    ref, hyp = cases()['1h_sparse']
    for name in ('numpy', 'scipy_c', 'numpy_c'):
        evaluate = backends[name][0]
        for workers in (1, 2, 4, 8):
            with ThreadPoolExecutor(max_workers=workers) as pool:
                def run():
                    return list(pool.map(lambda _: evaluate(ref, hyp), range(64)))
                measurement = measure(run, args.repeats)
            output['threads'].append({'backend': name, 'workers': workers,
                                      'tasks': 64, **measurement})
    args.output.write_text(json.dumps(output, indent=2) + '\n')


if __name__ == '__main__':
    main()
