"""Background execution for device I/O.

Every BMAP call is a blocking round-trip on a single RFCOMM channel. Three
rules follow, and this module enforces all of them:

1. **Never block the UI thread.** A request that waits on a sleeping
   headset would freeze the window for seconds.
2. **Never overlap requests.** The channel carries one request at a time;
   interleaving them desynchronises the reply stream (upstream's
   ``BmapDesyncError``). A lock serialises every operation, so a user
   dragging a slider cannot corrupt the reply to a concurrent read.
3. **Never touch Tk from a worker thread.** Tkinter is not thread-safe;
   ``widget.after()`` called off the main thread can silently never fire.
   The worker therefore hands results to a :class:`queue.Queue` and a
   main-thread poller delivers them — the only portable pattern.
"""

from __future__ import annotations

import queue
import threading
import traceback

__all__ = ["DeviceWorker"]

#: How often the main thread checks for finished jobs, in milliseconds.
POLL_INTERVAL_MS = 25


class _Job:
    __slots__ = ("fn", "args", "kwargs", "on_ok", "on_error", "label")

    def __init__(self, fn, args, kwargs, on_ok, on_error, label):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.on_ok = on_ok
        self.on_error = on_error
        self.label = label


class DeviceWorker:
    """Serialises device operations onto one background thread.

    Args:
        widget: Any Tk widget. Used only from the main thread, to schedule
            the result poller.
        on_busy: Called as ``on_busy(True/False, label)`` on the main thread
            as the in-flight operation count changes.
    """

    def __init__(self, widget, on_busy=None):
        self._widget = widget
        self._on_busy = on_busy
        self._jobs = queue.Queue()
        self._results = queue.Queue()
        self._pending = 0
        self._pending_lock = threading.Lock()
        self._stopped = False
        self._poll_job = None
        self._thread = threading.Thread(target=self._pump, name="bmap-io",
                                        daemon=True)
        self._thread.start()
        self._schedule_poll()

    # ── public API ──

    def run(self, fn, *args, on_ok=None, on_error=None, label="", **kwargs):
        """Queue ``fn`` for background execution.

        Args:
            fn: Callable to run off the UI thread.
            on_ok: Called on the UI thread with the return value.
            on_error: Called on the UI thread with the exception.
            label: Short description shown while the job runs.
        """
        with self._pending_lock:
            self._pending += 1
            depth = self._pending
        if self._on_busy and depth == 1:
            self._on_busy(True, label)
        self._jobs.put(_Job(fn, args, kwargs, on_ok, on_error, label))

    def stop(self):
        """Stop accepting work and cancel the poller."""
        self._stopped = True
        self._jobs.put(None)
        if self._poll_job is not None:
            try:
                self._widget.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None

    @property
    def busy(self):
        with self._pending_lock:
            return self._pending > 0

    # ── worker thread ──

    def _pump(self):
        while not self._stopped:
            job = self._jobs.get()
            if job is None:
                break
            try:
                result = job.fn(*job.args, **job.kwargs)
            except Exception as exc:  # noqa: BLE001 - reported to the UI
                self._results.put((job, None, exc))
            else:
                self._results.put((job, result, None))

    # ── main thread ──

    def _schedule_poll(self):
        if self._stopped:
            return
        try:
            self._poll_job = self._widget.after(POLL_INTERVAL_MS, self._drain)
        except Exception:
            self._poll_job = None

    def _drain(self):
        """Deliver finished jobs. Runs on the main thread only."""
        idle = False
        while True:
            try:
                job, result, error = self._results.get_nowait()
            except queue.Empty:
                break
            with self._pending_lock:
                self._pending = max(0, self._pending - 1)
                idle = self._pending == 0
            try:
                if error is not None:
                    if job.on_error:
                        job.on_error(error)
                    else:
                        _default_error_handler(error, job.label)
                elif job.on_ok:
                    job.on_ok(result)
            except Exception:
                traceback.print_exc()

        if idle and self._on_busy:
            try:
                self._on_busy(False, "")
            except Exception:
                pass
        self._schedule_poll()


def _default_error_handler(exc, label):
    """Last-resort handler so a missing callback cannot hide a failure."""
    import tkinter.messagebox as mb

    from pybmap.messages import error_hint, friendly_error
    message = friendly_error(exc)
    hint = error_hint(exc)
    if hint:
        message = "%s\n\n%s" % (message, hint)
    mb.showerror(label or "操作失败", message)
