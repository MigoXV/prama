"""Poetry build hook: compile the vendored C sources, never reuse a binary."""

from pathlib import Path
import os
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
NATIVE = ROOT / "src/prama/native"


def build_native(output: Path | None = None, *, sanitize: bool = False) -> Path:
    output = output or ROOT / "src/prama/lib/libsclite.so"
    output.parent.mkdir(parents=True, exist_ok=True)
    cc = shlex.split(os.environ.get("CC", "cc"))
    flags = [
        "-std=gnu11",
        "-fPIC",
        "-fvisibility=hidden",
        "-g",
        "-O1" if sanitize else "-O2",
        "-DSTDC_HEADERS=1",
    ]
    flags += shlex.split(os.environ.get("CFLAGS", ""))
    if sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    with tempfile.TemporaryDirectory(prefix="prama-build-") as tmp:
        objects = []
        for name in NATIVE.joinpath("sources.txt").read_text().split() + [
            "runtime.c",
            "bridge.c",
        ]:
            obj = Path(tmp) / (name + ".o")
            include = (
                []
                if name in ("runtime.c", "bridge.c")
                else ["-include", str(NATIVE / "runtime.h")]
            )
            subprocess.run(
                cc
                + flags
                + include
                + ["-I", str(NATIVE), "-c", str(NATIVE / name), "-o", str(obj)],
                check=True,
            )
            objects.append(str(obj))
        target = Path(tmp) / "libsclite.so"
        subprocess.run(
            cc
            + flags
            + ["-shared", "-Wl,-z,defs", "-Wl,-z,relro,-z,now", "-o", str(target)]
            + objects
            + ["-lm", "-pthread"]
            + shlex.split(os.environ.get("LDFLAGS", "")),
            check=True,
        )
        import shutil

        with tempfile.NamedTemporaryFile(
            dir=output.parent, prefix=".libsclite-", delete=False
        ) as staged:
            staged_path = Path(staged.name)
        try:
            shutil.copyfile(target, staged_path)
            os.replace(staged_path, output)
        finally:
            staged_path.unlink(missing_ok=True)
    return output


if __name__ == "__main__":
    build_native()
