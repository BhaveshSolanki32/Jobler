"""
Dedicated OS thread that owns the Playwright / Camoufox context.
Playwright's sync API uses greenlets and cannot be called from any thread
other than the one that created it.  Every browser operation must be
submitted here and runs serially inside this single thread.
"""
import queue
import threading
from typing import Any, Callable, Optional


class BrowserThread:
    _instance: Optional["BrowserThread"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="browser-thread"
        )
        self._thread.start()

    @classmethod
    def get(cls) -> "BrowserThread":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _run(self) -> None:
        while True:
            fn, result_q = self._queue.get()
            try:
                result = fn()
                if result_q is not None:
                    result_q.put((True, result))
            except Exception as exc:
                if result_q is not None:
                    result_q.put((False, exc))

    def submit(self, fn: Callable, timeout: float = 300) -> Any:
        """Run fn in the browser thread; block until done and return result."""
        result_q: queue.Queue = queue.Queue()
        self._queue.put((fn, result_q))
        ok, value = result_q.get(timeout=timeout)
        if not ok:
            raise value
        return value

    def fire(self, fn: Callable) -> None:
        """Submit fn without waiting — for operations that must stay open (login page)."""
        self._queue.put((fn, None))
