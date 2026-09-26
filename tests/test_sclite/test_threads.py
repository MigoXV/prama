from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from prama.evaluator import Evaluator, get_cer, get_wer, iter_cer, iter_wer
from prama.sclite import ScliteClient, ScliteOptions


def test_eight_concurrent_streams_with_cancellation():
    refs = ["Hello world", "你好世界", "a b a"] * 12
    hyps = ["hello word", "你好世", "a a b"] * 12
    expected = {"wer": get_wer(refs, hyps), "cer": get_cer(refs, hyps)}
    barrier = Barrier(8, timeout=15)

    def worker(index):
        metric = "wer" if index % 2 else "cer"
        factory = iter_wer if metric == "wer" else iter_cer
        for repeat in range(8):
            with factory(refs, hyps) as stream:
                first = next(stream)
                # Every native worker has begun before any consumer proceeds.
                barrier.wait()
                assert first.utterance == expected[metric].utterances[0]
                if index == 0 and repeat % 2 == 0:
                    continue
                events = [first, *stream]
                assert [event.utterance for event in events] == expected[
                    metric
                ].utterances
                assert stream.result() == expected[metric]
        return True

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(worker, range(8)))


def test_shared_evaluator_is_safe_for_threads():
    with Evaluator() as evaluator, ThreadPoolExecutor(max_workers=8) as pool:

        def task(index):
            method = evaluator.get_wer if index % 2 else evaluator.get_cer
            result = method(["hello world"], ["hello word"])
            assert result.summary.deletions == int(index % 2 == 0)
            assert result.summary.substitutions == int(index % 2 == 1)
            assert result.summary.ref_words == (2 if index % 2 else 10)

        list(pool.map(task, range(160)))


def test_encoding_case_and_reports_are_thread_isolated():
    barrier = Barrier(8, timeout=15)

    def task(index):
        sensitive = bool(index % 2)
        with ScliteClient() as client:
            for _ in range(20):
                barrier.wait()
                with client.align_texts(
                    "A café (s_1)\n",
                    "a x (s_1)\n",
                    ref_format="trn",
                    hyp_format="trn",
                    options=ScliteOptions(encoding="UTF-8", case_sensitive=sensitive),
                ) as result:
                    assert result.summary().substitutions == 1 + int(sensitive)
                    assert result.tokens()[0].eval_label == (
                        "substitution" if sensitive else "correct"
                    )
                    assert "s_1" in result.report_text("sgml")
                    assert "s_1" in result.report_text("pra")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(task, range(8)))


def test_different_encodings_are_isolated_between_threads():
    barrier = Barrier(8, timeout=15)

    def task(index):
        unicode = bool(index % 2)
        options = ScliteOptions(
            encoding="UTF-8" if unicode else "ASCII", char_align_flags=1
        )
        with ScliteClient() as client:
            for _ in range(10):
                barrier.wait()
                with client.align_texts(
                    "世界 (s_1)\n",
                    "世 (s_1)\n",
                    ref_format="trn",
                    hyp_format="trn",
                    options=options,
                ) as result:
                    assert result.summary().ref_words == (2 if unicode else 6)
                    assert result.summary().deletions == (1 if unicode else 3)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(task, range(8)))
