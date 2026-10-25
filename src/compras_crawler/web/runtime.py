from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
from typing import Any, Iterator
import fcntl
import os
import shutil
import subprocess
import sys
import time
import uuid

from ..crawl_state import CrawlStopped
from .store import AppStore


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("o workspace ou município já está em uso") from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class WorkerControl:
    def __init__(self, store: AppStore, run_id: str, owner: str, parent_pid: int,
                 reserve_bytes: int = 5 * 1024**3):
        self.store, self.run_id, self.owner = store, run_id, owner
        self.parent_pid, self.reserve_bytes = parent_pid, reserve_bytes

    def check(self) -> None:
        if os.getppid() != self.parent_pid:
            raise CrawlStopped("serviço encerrado")
        status = self.store.worker_status(self.run_id, self.owner)
        if status not in ("running", "projecting"):
            raise CrawlStopped("parada solicitada ou execução recuperada por outro serviço")
        if shutil.disk_usage(self.store.root).free < self.reserve_bytes:
            raise OSError("reserva mínima de espaço em disco atingida; Bronze preservado")

    def wait(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while True:
            self.check()
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.25, remaining))


class SharedThrottle:
    """A single request gate, including auth retries and cooldown, across processes."""
    def __init__(self, store: AppStore, control: Any, interval: float = 1.0):
        self.store, self.control, self.interval = store, control, interval

    def wait(self) -> None:
        while True:
            self.control.check()
            with self.store.connect() as con:
                con.execute("BEGIN IMMEDIATE")
                now = time.time()
                next_at = con.execute("SELECT next_at FROM request_gate WHERE id=1").fetchone()[0]
                if next_at <= now:
                    con.execute("UPDATE request_gate SET next_at=? WHERE id=1", [now + self.interval])
                    con.execute("COMMIT")
                    return
                con.execute("COMMIT")
            self.control.wait(min(0.25, next_at - now))

    def pause_for(self, seconds: float) -> None:
        if seconds > 0:
            with self.store.connect() as con:
                con.execute("UPDATE request_gate SET next_at=max(next_at,?) WHERE id=1", [time.time() + seconds])


class Service:
    def __init__(self, store: AppStore, *, max_workers: int = 2, reserve_bytes: int = 5 * 1024**3):
        self.store, self.max_workers, self.reserve_bytes = store, max_workers, reserve_bytes
        self.instance = str(uuid.uuid4())
        self.stop_event = Event()
        self.processes: dict[str, subprocess.Popen] = {}
        self.thread: Thread | None = None
        self.error: str | None = None
        self._lock = None

    def start(self) -> None:
        self._lock = file_lock(self.store.root / "service.lock")
        self._lock.__enter__()
        try:
            self.store.begin_service(self.instance)
            self.thread = Thread(target=self._loop, name="compras-scheduler", daemon=True)
            self.thread.start()
        except BaseException:
            self._lock.__exit__(*sys.exc_info())
            self._lock = None
            raise

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.error = None
                self.tick()
            except Exception as exc:
                self.error = str(exc)[:1000]
            self.stop_event.wait(1)

    def tick(self) -> None:
        for run_id, process in list(self.processes.items()):
            if process.poll() is not None:
                run = self.store.run(run_id)
                if run["status"] in ("running", "projecting", "interrupted"):
                    self.store.recover_worker(run_id, self.instance)
                elif run["status"] == "stopping":
                    self.store.update_run(run_id, self.instance, "stopped")
                del self.processes[run_id]
        self.store.tick_schedules()
        if shutil.disk_usage(self.store.root).free < self.reserve_bytes:
            self.error = "Novas coletas bloqueadas: reserva mínima de espaço em disco atingida."
            return
        while not self.stop_event.is_set() and len(self.processes) < self.max_workers:
            run = self.store.claim(self.instance, max_workers=self.max_workers)
            if run is None:
                return
            try:
                process = subprocess.Popen(
                    [sys.executable, "-m", "compras_crawler.web.worker", str(self.store.root), run["id"],
                     self.instance, str(os.getpid()), str(self.reserve_bytes)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                self.processes[run["id"]] = process
            except OSError as exc:
                self.store.update_run(run["id"], self.instance, "failed", error=str(exc))

    def close(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join()
        # Revocation is observed during waits and before the next request. City
        # flocks fence a worker still finishing its current HTTP call on restart.
        with self.store.connect() as con:
            con.execute("DELETE FROM service WHERE instance=?", [self.instance])
        deadline = time.monotonic() + 3
        for process in self.processes.values():
            try:
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
        if self._lock:
            self._lock.__exit__(None, None, None)
            self._lock = None
