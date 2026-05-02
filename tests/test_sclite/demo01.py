from __future__ import annotations


from prama.evaluator import get_cer, get_wer


def main() -> None:
    references = [
        "the quick brown fox jumps over the lazy dog",
        "speech recognition is useful",
    ]
    hypotheses = [
        "the quick brown fox jumped over lazy dog",
        "speech recognition is very useful",
    ]
    utterance_ids = ["fox-demo", "asr-demo"]

    wer = get_wer(references, hypotheses, utterance_ids)
    cer = get_cer(references, hypotheses, utterance_ids)

    print(f"WER: {wer.wer:.2f}%")
    print(f"CER: {cer.cer:.2f}%")
    print("Utterances:", [utterance.id for utterance in wer.utterances])
    print(
        "Errors:",
        {
            "substitutions": wer.summary.substitutions,
            "deletions": wer.summary.deletions,
            "insertions": wer.summary.insertions,
        },
    )


if __name__ == "__main__":
    main()
