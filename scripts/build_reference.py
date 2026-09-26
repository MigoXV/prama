"""Build an untouched SCTK reference in an isolated output directory."""

from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("tmo-workspace/SCTK"))
    parser.add_argument("--output", type=Path, default=Path("build/original"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "sclite"
    shutil.copytree(args.source / "src/sclite", target, dirs_exist_ok=True)
    with (args.output / "configure.log").open("w") as log:
        subprocess.run(
            ["bash", "config.sh"],
            cwd=target,
            input="no\nno\n",
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    with (args.output / "build.log").open("w") as log:
        subprocess.run(
            ["make", "-j4", "sclite", "sctkUnit"],
            cwd=target,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    metadata = {
        "revision": subprocess.check_output(
            ["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True
        ).strip(),
        "sha256": hashlib.sha256((target / "sclite").read_bytes()).hexdigest(),
        "configure_answers": ["no GNU diff", "no SLM"],
        "compiler": subprocess.check_output(
            ["cc", "--version"], text=True
        ).splitlines()[0],
    }
    (args.output / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(target / "sclite")


if __name__ == "__main__":
    main()
