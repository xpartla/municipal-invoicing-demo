"""Running the worker in a background thread of the app (started and stopped by the
lifespan from P2-M0-T05) or in the foreground (`riso worker`)."""

import logging
import threading

from riso.jobs.application.worker import Worker

log = logging.getLogger(__name__)


class WorkerThread:
    def __init__(self, worker: Worker, *, poll_interval: float = 1.0) -> None:
        self._worker = worker
        self._poll = poll_interval
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name=f"riso-worker-{self._worker.worker_id}", daemon=True
        )
        self._thread.start()

    def wake(self) -> None:
        """Asks the loop to look for jobs now instead of at the next poll."""
        self._wake.set()

    def stop(self, timeout: float = 10.0) -> bool:
        """Stops after the job in hand, if any. Returns True when the thread has ended."""
        self._stop.set()
        self._wake.set()
        if self._thread is None:
            return True
        self._thread.join(timeout)
        stopped = not self._thread.is_alive()
        if stopped:
            self._thread = None
        return stopped

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                while not self._stop.is_set() and self._worker.run_once():
                    pass
            except Exception:
                log.exception("worker %s: unexpected error", self._worker.worker_id)
            self._wake.wait(self._poll)
            self._wake.clear()
