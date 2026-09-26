"""Bounded native callback bridge. Use a context manager for early termination."""

from __future__ import annotations

import ctypes
from dataclasses import replace
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread

from prama._sclite_client import ScliteClient, ScliteResult, _decode
from prama._sclite_native import CCounts, RecordCallback
from prama._sclite_types import ScliteCounts, ScliteError, ScliteRecord


class _State:
    def __init__(self):
        self.queue: Queue[ScliteRecord] = Queue(maxsize=16)
        self.cancel = Event()
        self.done = Event()
        self.result: ScliteResult | None = None
        self.error: BaseException | None = None


def _produce(state, lib_path, ref, hyp, kwargs):
    sequence = 0

    def notify(_user, pointer, group, utterance):
        nonlocal sequence
        if state.cancel.is_set():
            return 1
        try:
            with ScliteResult(
                client._lib, client._ctx, pointer, [], borrowed=True
            ) as view:
                item = view.utterance(group, utterance)
                tokens = tuple(view.tokens(group, utterance))
                name, raw = ctypes.c_char_p(), CCounts()
                if client._lib.sclite_result_group_summary(
                    pointer, group, ctypes.byref(name), ctypes.byref(raw)
                ):
                    raise ScliteError("cannot read streaming group")
                c, s, d, i = (
                    sum(t.eval == flag for t in tokens) for flag in (1, 2, 8, 4)
                )
                n = c + s + d
                counts = ScliteCounts(
                    n,
                    c + s + i,
                    c,
                    s,
                    d,
                    i,
                    1,
                    int(s + d + i > 0),
                    (s + d + i) / n * 100 if n else 0.0,
                    100.0 - ((s + d + i) / n * 100 if n else 0.0),
                )
                event = ScliteRecord(
                    sequence,
                    group,
                    utterance,
                    _decode(name.value),
                    item,
                    tokens,
                    counts,
                    view.summary(),
                )
            while not state.cancel.is_set():
                try:
                    state.queue.put(event, timeout=0.05)
                    sequence += 1
                    return 0
                except Full:
                    pass
            return 1
        except BaseException as exc:
            state.error = exc
            return 1

    try:
        with ScliteClient(lib_path) as client:
            callback = RecordCallback(notify)
            state.result = client.align_texts(ref, hyp, **kwargs, _callback=callback)
    except BaseException as exc:
        if state.error is None:
            state.error = exc
    finally:
        state.done.set()


class ScliteStream:
    """Lazy producer; result() is available after iterator exhaustion.

    close() cancels and joins the producer. Events are detached Python values;
    the native final result is owned by this stream and closes with it.
    """

    def __init__(self, lib_path, ref, hyp, **kwargs):
        self._state = _State()
        if kwargs.get("options") is not None:
            kwargs["options"] = replace(kwargs["options"])
        self._args = (self._state, lib_path, ref, hyp, kwargs)
        self._thread: Thread | None = None
        self._closed = False
        self._exhausted = False
        self._lock = Lock()
        self._close_lock = Lock()

    def __enter__(self) -> ScliteStream:
        if self._closed:
            raise ScliteError("stream is closed")
        return self

    def __exit__(self, *_):
        self.close()

    def __iter__(self) -> ScliteStream:
        return self

    def __next__(self) -> ScliteRecord:
        with self._lock:
            if self._closed:
                raise ScliteError("stream is closed")
            if self._exhausted:
                raise StopIteration
            if self._thread is None:
                self._thread = Thread(
                    target=_produce, args=self._args, name="prama-sclite"
                )
                self._thread.start()
                self._args = None
        while not self._state.cancel.is_set():
            try:
                return self._state.queue.get(timeout=0.05)
            except Empty:
                if self._state.done.is_set():
                    if self._state.error is not None:
                        raise self._state.error
                    self._exhausted = True
                    raise StopIteration
        raise ScliteError("stream is closed")

    def result(self) -> ScliteResult:
        if self._closed or not self._exhausted:
            raise ScliteError("final result requires an exhausted, open stream")
        if self._state.error:
            raise self._state.error
        assert self._state.result is not None
        return self._state.result

    def close(self) -> None:
        with self._close_lock:
            self._close()

    def _close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._state.cancel.set()
            thread = self._thread
        if thread is not None:
            thread.join()
        if self._state.result is not None:
            self._state.result.close()
        while True:
            try:
                self._state.queue.get_nowait()
            except Empty:
                break
        self._args = None
        self._state.error = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
