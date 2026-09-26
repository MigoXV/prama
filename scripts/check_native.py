"""Build isolated native harnesses and run leak/race/sanitizer checks."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_native import build_native


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loops", type=int, default=10000)
    parser.add_argument("--thread-loops", type=int, default=1250)
    parser.add_argument("--checker-thread-loops", type=int, default=100)
    args = parser.parse_args()
    output = ROOT / "outputs/native-checks"
    output.mkdir(parents=True, exist_ok=True)
    for sanitized in (False, True):
        mode = "sanitized" if sanitized else "regular"
        directory = ROOT / "build/native-checks" / mode
        directory.mkdir(parents=True, exist_ok=True)
        build_native(directory / "libsclite.so", sanitize=sanitized)
        for source in ("native_stress", "native_threads", "native_corpus"):
            flags = (
                ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
                if sanitized
                else []
            )
            subprocess.run(
                [
                    "cc",
                    "-g",
                    "-pthread",
                    *flags,
                    "-I",
                    str(ROOT / "src/prama/native"),
                    str(ROOT / "scripts" / f"{source}.c"),
                    "-L",
                    str(directory),
                    "-lsclite",
                    f"-Wl,-rpath,{directory}",
                    "-o",
                    str(directory / source),
                ],
                check=True,
            )
        jobs = [
            ("native_stress", [str(args.loops)]),
            (
                "native_threads",
                [str(args.thread_loops if sanitized else args.checker_thread_loops)],
            ),
            ("native_corpus", [str(ROOT / "tests/data/upstream")]),
        ]
        for name, extra in jobs:
            env = dict(os.environ)
            if sanitized:
                env.update(
                    ASAN_OPTIONS="detect_leaks=1:halt_on_error=1",
                    UBSAN_OPTIONS="halt_on_error=1",
                )
                prefix = []
            else:
                env["GLIBC_TUNABLES"] = "glibc.pthread.stack_cache_size=0"
                prefix = [
                    "valgrind",
                    "--leak-check=full",
                    "--show-leak-kinds=all",
                    "--errors-for-leak-kinds=definite,indirect",
                    "--error-exitcode=99",
                    f"--log-file={output / (name + '-valgrind.log')}",
                ]
            with (output / f"{name}-{mode}.log").open("w") as log:
                subprocess.run(
                    [*prefix, str(directory / name), *extra],
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
    with (output / "threads-helgrind-output.log").open("w") as log:
        subprocess.run(
            [
                "valgrind",
                "--tool=helgrind",
                "--error-exitcode=99",
                f"--log-file={output / 'helgrind.log'}",
                str(ROOT / "build/native-checks/regular/native_threads"),
                str(args.checker_thread_loops),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    print(f"All native checks passed; logs: {output}")


if __name__ == "__main__":
    main()
