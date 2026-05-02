from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from prama.evaluator import Evaluator


def main() -> None:
    references = ["hello world", "你好世界"]
    hypotheses = ["hello word", "你好世"]
    utterance_ids = ["english-demo", "chinese-demo"]

    with Evaluator() as evaluator:
        wer = evaluator.get_wer(references, hypotheses, utterance_ids)
        cer = evaluator.get_cer(references, hypotheses, utterance_ids)

    print("References:", references)
    print("Hypotheses:", hypotheses)
    print("Utterances:", [utterance.id for utterance in wer.utterances])
    print(f"WER: {wer.wer:.2f}%")
    print(f"CER: {cer.cer:.2f}%")


if __name__ == "__main__":
    main()
