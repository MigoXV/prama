"""Build and test real distributions in independent Poetry environments."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def command(args, cwd, env, log):
    log.write(f"\n$ {' '.join(map(str, args))}\n")
    log.flush()
    subprocess.run(
        list(map(str, args)),
        cwd=cwd,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        check=True,
    )


def install_and_test(wheel, directory, reference, env, log):
    directory.mkdir()
    (directory / "pyproject.toml").write_text(f"""[tool.poetry]
name = "prama-artifact-check"
version = "0.0.0"
package-mode = false
[tool.poetry.dependencies]
python = ">=3.10,<3.13"
prama = {{path = {json.dumps(str(wheel.resolve()))}}}
pytest = ">=9,<10"
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
""")
    isolated_env = dict(env, POETRY_VIRTUALENVS_IN_PROJECT="true")
    command(["poetry", "env", "use", sys.executable], directory, isolated_env, log)
    command(["poetry", "install", "--no-interaction"], directory, isolated_env, log)
    shutil.copytree(
        ROOT / "tests",
        directory / "tests",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (directory / "scripts").mkdir()
    shutil.copy2(
        ROOT / "scripts/check_alignment.py", directory / "scripts/check_alignment.py"
    )
    isolated_env["SCLITE_REFERENCE"] = str(reference.resolve())
    # The consumer does not need a compiler, a source checkout, or an old .so.
    isolated_env["CC"] = "/compiler-must-not-be-needed"
    command(
        [
            "poetry",
            "run",
            "python",
            "-c",
            """from pathlib import Path
import prama, sys
from prama.sclite import ScliteClient
root=Path(sys.prefix).resolve()
assert Path(prama.__file__).resolve().is_relative_to(root)
with ScliteClient() as c:
    assert Path(c.lib_path).resolve().is_relative_to(root)
    print("installed package:",prama.__file__)
    print("loaded native library:",c.lib_path)
""",
        ],
        directory,
        isolated_env,
        log,
    )
    command(["poetry", "run", "pytest", "-q"], directory, isolated_env, log)
    command(
        [
            "poetry",
            "run",
            "python",
            "scripts/check_alignment.py",
            "--cli",
            reference.resolve(),
            "--count",
            "10000",
        ],
        directory,
        isolated_env,
        log,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference", type=Path, default=ROOT / "build/original/sclite/sclite"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/distribution")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    for key in ("PYTHONPATH", "SCLITE_LIB_PATH", "VIRTUAL_ENV", "POETRY_ACTIVE"):
        env.pop(key, None)
    with (args.output / "verification.log").open("w") as log:
        # Remove only this project's generated native file and release artifacts.
        (ROOT / "src/prama/lib/libsclite.so").unlink(missing_ok=True)
        for pattern in ("prama-*.whl", "prama-*.tar.gz"):
            for old in (ROOT / "dist").glob(pattern):
                old.unlink()
        command(["poetry", "build"], ROOT, env, log)
        wheel = next((ROOT / "dist").glob("*.whl"))
        sdist = next((ROOT / "dist").glob("*.tar.gz"))
        with zipfile.ZipFile(wheel) as archive:
            assert "prama/lib/libsclite.so" in archive.namelist()
            metadata = archive.read(
                next(n for n in archive.namelist() if n.endswith(".dist-info/WHEEL"))
            ).decode()
            assert "Root-Is-Purelib: false" in metadata and "-any" not in metadata
        with tarfile.open(sdist) as archive:
            names = archive.getnames()
            assert any(n.endswith("/build_native.py") for n in names)
            assert any(n.endswith("/native/bridge.c") for n in names)
            assert not any(n.endswith(".so") for n in names)
        # The directories are outside the repository and retained on failure.
        workspace = Path(tempfile.mkdtemp(prefix="prama-distribution-"))
        log.write(f"artifact workspace: {workspace}\n")
        log.flush()
        install_and_test(wheel, workspace / "wheel-consumer", args.reference, env, log)
        with tarfile.open(sdist) as archive:
            archive.extractall(workspace / "sdist", filter="data")
        source = next((workspace / "sdist").iterdir())
        command(["poetry", "env", "use", sys.executable], source, env, log)
        command(["poetry", "build"], source, env, log)
        rebuilt = next((source / "dist").glob("*.whl"))
        install_and_test(
            rebuilt, workspace / "sdist-consumer", args.reference, env, log
        )
        command(["readelf", "-d", ROOT / "src/prama/lib/libsclite.so"], ROOT, env, log)
        command(["ldd", ROOT / "src/prama/lib/libsclite.so"], ROOT, env, log)
        metadata = {
            "status": "passed",
            "workspace": str(workspace),
            "python": sys.version,
            "artifacts": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (wheel, sdist)
            },
        }
        (args.output / "result.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
