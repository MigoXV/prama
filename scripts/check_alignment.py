"""Reproducible CLI / native / streamed / legacy differential verification."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import random
import re
import subprocess
import tempfile

from prama.sclite import IdType, ScliteClient, ScliteOptions


def normalize(report: str) -> str:
    report = re.sub(
        r'(ref_fname|hyp_fname|creation_date)="[^"]*"', r'\1="NORMALIZED"', report
    )
    report = re.sub(
        r"^(Ref file:|Hyp file:|Creation date:).*$",
        r"\1 NORMALIZED",
        report,
        flags=re.M,
    )
    return report


def snapshot(result):
    return {
        "summary": asdict(result.summary()),
        "groups": [asdict(g) for g in result.groups()],
        "utterances": [
            [
                {
                    "metadata": asdict(u),
                    "tokens": [asdict(t) for t in result.tokens(g, i)],
                }
                for i, u in enumerate(result.utterances(g))
            ]
            for g in range(len(result.groups()))
        ],
        "reports": {
            name: normalize(result.report_text(name))
            for name in ("sys", "raw", "pra", "prf", "sgml")
        },
    }


def check_case(
    cli,
    ref,
    hyp,
    *,
    ref_format="trn",
    hyp_format="trn",
    options=None,
    flags=(),
    legacy=None,
):
    options = options or ScliteOptions(id_type=IdType.SPU_ID, encoding="UTF-8")
    kwargs = dict(ref_format=ref_format, hyp_format=hyp_format, options=options)
    with ScliteClient() as client, client.align_texts(ref, hyp, **kwargs) as result:
        expected = snapshot(result)
    with (
        ScliteClient() as client,
        client.iter_align_texts(ref, hyp, **kwargs) as stream,
    ):
        events = list(stream)
        assert snapshot(stream.result()) == expected, "stream final differs from batch"
        for seq, event in enumerate(events):
            assert event.sequence == seq
            record = expected["utterances"][event.group_index][event.utterance_index]
            assert asdict(event.utterance) == record["metadata"]
            assert [asdict(t) for t in event.tokens] == record["tokens"]
        assert len(events) == sum(map(len, expected["utterances"]))
        if events:
            assert asdict(events[-1].cumulative) == expected["summary"]
    with tempfile.TemporaryDirectory(prefix="prama-oracle-") as tmp:
        rp, hp = Path(tmp) / "ref", Path(tmp) / "hyp"
        rp.write_text(ref)
        hp.write_text(hyp)
        args = [
            str(cli),
            "-r",
            str(rp),
            ref_format,
            "-h",
            str(hp),
            hyp_format,
            "memory",
            "-f",
            "0",
            "-e",
            "utf-8",
        ]
        if ref_format == "trn":
            args += [
                "-i",
                {
                    IdType.SPU_ID: "spu_id",
                    IdType.SP: "sp",
                    IdType.WSJ: "wsj",
                    IdType.RM: "rm",
                    IdType.ATIS: "atis",
                    IdType.SWB: "swb",
                }[options.id_type],
            ]
        for report in ("sys", "raw", "pra", "prf", "sgml"):
            completed = subprocess.run(
                args
                + list(flags)
                + ["-o", {"sys": "sum", "raw": "rsum"}.get(report, report), "stdout"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert normalize(completed.stdout) == expected["reports"][report], (
                f"CLI {report} differs"
            )
    legacy_difference = None
    if legacy:
        with (
            ScliteClient(legacy) as client,
            client.align_texts(ref, hyp, **kwargs) as result,
        ):
            old = snapshot(result)
            if old != expected:
                fields = [k for k in expected if expected[k] != old[k]]
                reports = [
                    k
                    for k in expected["reports"]
                    if expected["reports"][k] != old["reports"][k]
                ]
                sequence_only = fields == ["reports"] and all(
                    re.sub(
                        r'sequence="\d+"',
                        'sequence="NORMALIZED"',
                        expected["reports"][k],
                    )
                    == re.sub(
                        r'sequence="\d+"', 'sequence="NORMALIZED"', old["reports"][k]
                    )
                    for k in reports
                )
                legacy_difference = {
                    "fields": fields,
                    "reports": reports,
                    "sequence_only": sequence_only,
                }
    return legacy_difference


def generated(seed, count):
    rng = random.Random(seed)
    vocabulary = [
        "a",
        "b",
        "c",
        "one",
        "two",
        "hello",
        "World",
        "你",
        "好",
        "世界",
        "café",
        "🙂",
    ]
    for i in range(count):
        ref = rng.choices(vocabulary, k=rng.randrange(0, 18))
        hyp = list(ref)
        for _ in range(rng.randrange(0, 6)):
            op = rng.randrange(3)
            if op == 0 or not hyp:
                hyp.insert(rng.randrange(len(hyp) + 1), rng.choice(vocabulary))
            elif op == 1:
                hyp.pop(rng.randrange(len(hyp)))
            else:
                hyp[rng.randrange(len(hyp))] = rng.choice(vocabulary)
        yield " ".join(ref), " ".join(hyp), f"s{i % 7}_{i:06d}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--legacy", type=Path)
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument(
        "--output", type=Path, default=Path("outputs/differential.json")
    )
    args = parser.parse_args()
    rows = list(generated(20260926, args.count))
    differences = []
    batches = 0
    for metric in ("wer", "cer"):
        for start in range(0, len(rows), 100):
            group = rows[start : start + 100]
            ref = "".join(f"{r} ({i})\n" for r, h, i in group)
            hyp = "".join(f"{h} ({i})\n" for r, h, i in group)
            try:
                delta = check_case(
                    args.cli,
                    ref,
                    hyp,
                    options=ScliteOptions(
                        encoding="UTF-8", char_align_flags=int(metric == "cer")
                    ),
                    flags=["-c"] if metric == "cer" else [],
                    legacy=args.legacy,
                )
            except BaseException:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.with_suffix(".ref.trn").write_text(ref)
                args.output.with_suffix(".hyp.trn").write_text(hyp)
                raise
            if delta:
                differences.append({"metric": metric, "start": start, **delta})
            batches += 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "seed": 20260926,
                "pairs": len(rows),
                "metrics": ["wer", "cer"],
                "batches": batches,
                "legacy_differences": differences,
                "status": "passed",
            },
            indent=2,
        )
        + "\n"
    )
    print(args.output.read_text())


if __name__ == "__main__":
    main()
