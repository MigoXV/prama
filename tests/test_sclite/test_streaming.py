from __future__ import annotations

from threading import Event, Thread

import pytest

from prama.evaluator import get_cer, get_wer, iter_cer, iter_wer
from prama.sclite import ScliteClient, ScliteError, ScliteOptions


@pytest.mark.parametrize("batch,streaming", [(get_wer, iter_wer), (get_cer, iter_cer)])
def test_high_level_stream(batch, streaming):
    refs = ["hello world", "你好世界", "a b a", ""]
    hyps = ["hello word", "你好世", "a a b", "x"]
    expected = batch(refs, hyps)
    with streaming(refs, hyps) as stream:
        with pytest.raises(ScliteError, match="exhausted"):
            stream.result()
        events = list(stream)
        assert [e.utterance for e in events] == expected.utterances
        assert events[-1].cumulative == expected.summary
        result = stream.result()
        assert result == expected
    assert result.summary == expected.summary


def test_native_completion_barrier(monkeypatch):
    # Stall the second native record's Python materialization. The first event
    # must be observable while native alignment is still inside that callback.
    from prama._sclite_client import ScliteResult

    entered, release = Event(), Event()
    original = ScliteResult.utterance

    def gated(self, g=0, u=0):
        if self._borrowed and u == 1:
            entered.set()
            assert release.wait(5)
        return original(self, g, u)

    monkeypatch.setattr(ScliteResult, "utterance", gated)
    with (
        ScliteClient() as client,
        client.iter_align_texts(
            "a (s_1)\nb (s_2)\n",
            "a (s_1)\nb (s_2)\n",
            ref_format="trn",
            hyp_format="trn",
        ) as stream,
    ):
        try:
            first = next(stream)
            assert first.utterance.id == "(s_1)"
            assert entered.wait(5)
            assert not stream._state.done.is_set()
        finally:
            release.set()
        assert len(list(stream)) == 1


def test_queue_is_bounded_and_close_joins():
    text = "".join(f"a (s_{i})\n" for i in range(1000))
    with ScliteClient() as client:
        stream = client.iter_align_texts(text, text, ref_format="trn", hyp_format="trn")
        next(stream)
        # Explicit close must work even when producer is blocked on put().
        stream.close()
        assert stream._state.queue.qsize() == 0
        assert not stream._thread.is_alive()
        stream.close()
        with pytest.raises(ScliteError):
            stream.result()


def test_close_client_cancels_active_stream():
    client = ScliteClient()
    text = "".join(f"a (s_{i})\n" for i in range(100))
    stream = client.iter_align_texts(text, text, ref_format="trn", hyp_format="trn")
    next(stream)
    thread = Thread(target=client.close)
    thread.start()
    thread.join(5)
    assert not thread.is_alive()
    assert not stream._thread.is_alive()


def test_background_failure_preserves_delivered_events(monkeypatch):
    from prama._sclite_client import ScliteResult

    original = ScliteResult.utterance

    def failing(self, g=0, u=0):
        if self._borrowed and u == 1:
            raise RuntimeError("record conversion failed")
        return original(self, g, u)

    monkeypatch.setattr(ScliteResult, "utterance", failing)
    with (
        ScliteClient() as client,
        client.iter_align_texts(
            "a (s_1)\nb (s_2)\n",
            "a (s_1)\nb (s_2)\n",
            ref_format="trn",
            hyp_format="trn",
        ) as stream,
    ):
        first = next(stream)
        with pytest.raises(RuntimeError, match="conversion failed"):
            next(stream)
        assert first.tokens[0].ref_word == "a"
        with pytest.raises(ScliteError):
            stream.result()


def test_options_do_not_bleed_between_operations():
    with ScliteClient() as c:
        for sensitive in (True, False, True, False):
            with c.align_texts(
                "A (s_1)\n",
                "a (s_1)\n",
                ref_format="trn",
                hyp_format="trn",
                options=ScliteOptions(case_sensitive=sensitive),
            ) as r:
                assert r.summary().substitutions == int(sensitive)


def test_other_threads_work_while_a_stream_is_paused(monkeypatch):
    from prama._sclite_client import ScliteResult

    entered, release = Event(), Event()
    original = ScliteResult.utterance

    def gated(self, g=0, u=0):
        if self._borrowed and u == 1:
            entered.set()
            assert release.wait(5)
        return original(self, g, u)

    monkeypatch.setattr(ScliteResult, "utterance", gated)
    text = "a (s_1)\nb (s_2)\n"
    with (
        ScliteClient() as c,
        c.iter_align_texts(text, text, ref_format="trn", hyp_format="trn") as stream,
    ):
        try:
            next(stream)
            assert entered.wait(5)
            assert get_wer(["a"], ["a"]).summary.correct == 1
        finally:
            release.set()
        list(stream)


def test_repeated_streams_release_threads_and_file_descriptors():
    import gc
    import os
    import threading

    before = len(os.listdir("/proc/self/fd"))
    text = "".join(f"a (s_{i})\n" for i in range(30))
    with ScliteClient() as client:
        for _ in range(200):
            with client.iter_align_texts(
                text, text, ref_format="trn", hyp_format="trn"
            ) as stream:
                assert next(stream).counts.correct == 1
    gc.collect()
    assert not any(t.name == "prama-sclite" for t in threading.enumerate())
    assert len(os.listdir("/proc/self/fd")) == before
