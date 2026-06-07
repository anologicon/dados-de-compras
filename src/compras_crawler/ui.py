from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import get_terminal_size
from time import monotonic
from typing import TextIO
import os
import sys
import threading


@dataclass(frozen=True)
class RunContext:
    run_id: str
    db_path: Path
    base_url: str
    scope: str
    start_date: str | None
    end_date: str | None
    page_size: int | None
    resume: bool
    total_jobs: int


class ConsoleUI:
    SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, stream: TextIO | None = None, *, color: bool | None = None):
        self.stream = stream or sys.stdout
        self._tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self._color = self._tty if color is None else color
        self._started_at = monotonic()
        self._job_started_at = monotonic()
        self._total_pages = 0
        self._total_rows = 0
        self._jobs_done = 0
        self._total_jobs = 1
        self._current_job_index = 0
        self._current_job_rows = 0
        self._current_job_pages = 0
        self._current_job_name = ""
        self._current_page = 0
        self._current_spinner_message = ""
        self._live_len = 0
        self._spinner_thread: threading.Thread | None = None
        self._spinner_stop = threading.Event()
        self._spinner_lock = threading.Lock()
        self._spinner_frame = 0

    def start(self, *, ctx: RunContext) -> None:
        self._total_jobs = max(ctx.total_jobs, 1)
        self._write_line(self._style("compras-crawler sync", "cyan", bold=True))
        self._write_line(f"run id:   {ctx.run_id}")
        self._write_line(f"db path:  {ctx.db_path}")
        self._write_line(f"base url: {ctx.base_url}")
        self._write_line(f"scope:    {ctx.scope}")
        if ctx.start_date or ctx.end_date:
            self._write_line(f"date:     {ctx.start_date or '-'} → {ctx.end_date or '-'}")
        if ctx.page_size is not None:
            self._write_line(f"page size: {ctx.page_size}")
        self._write_line(f"resume:   {'yes' if ctx.resume else 'no'}")
        self._write_line(f"jobs:     {ctx.total_jobs}")
        self._write_line("")

    def job_started(self, *, index: int, total: int, job_name: str, entity_name: str, path: str, start_page: int, resume: bool) -> None:
        self._stop_spinner()
        self._current_job_index = index
        self._current_job_rows = 0
        self._current_job_pages = 0
        self._current_job_name = job_name
        self._current_page = start_page
        self._job_started_at = monotonic()
        self._write_line(self._style(f"▶ [{index}/{total}] {job_name} ({entity_name})", "cyan", bold=True))
        self._write_line(f"  path: {path}")
        self._write_line(f"  page: {start_page}{' (resumed)' if resume else ''}")
        self._render_status("queued")

    def fetch_started(self, *, job_name: str, page_number: int, path: str) -> None:
        message = f"fetching {job_name} page {page_number} · {path}"
        if self._tty:
            self._current_spinner_message = message
            self._spinner_stop.clear()
            if not self._spinner_thread or not self._spinner_thread.is_alive():
                self._spinner_thread = threading.Thread(target=self._spin, daemon=True)
                self._spinner_thread.start()
        else:
            self._write_line(self._style(f"… {message}", "yellow"))

    def fetch_finished(
        self,
        *,
        job_name: str,
        page_number: int,
        status_code: int,
        elapsed_seconds: float,
        record_count: int,
        content_type: str,
    ) -> None:
        self._stop_spinner()
        text = (
            f"✓ fetched {job_name} page {page_number} | HTTP {status_code} | {record_count} rows | "
            f"{self._format_duration(elapsed_seconds)}"
        )
        self._write_line(self._style(text, "green", bold=True))

    def page_done(self, *, job_name: str, page_number: int, status_code: int, record_count: int) -> None:
        self._total_pages += 1
        self._total_rows += record_count
        self._current_job_pages += 1
        self._current_job_rows += record_count
        self._current_page = page_number + 1
        self._render_status(f"{job_name} page {page_number} done")

    def job_finished(self, *, job_name: str, next_page: int) -> None:
        self._stop_spinner()
        elapsed = monotonic() - self._job_started_at
        text = (
            f"✓ [{self._current_job_index}] {job_name} done | pages={self._current_job_pages} | "
            f"rows={self._current_job_rows} | next page={next_page} | {self._format_duration(elapsed)}"
        )
        self._write_line(self._style(text, "green", bold=True))
        self._write_line("")
        self._jobs_done += 1
        self._render_status("waiting")

    def run_finished(self, *, run_id: str, status: str) -> None:
        self._stop_spinner()
        elapsed = monotonic() - self._started_at
        self._write_line(
            self._style(
                f"{status.upper()}: run {run_id} | jobs={self._jobs_done} | pages={self._total_pages} | rows={self._total_rows} | {self._format_duration(elapsed)}",
                "green" if status == "finished" else "red",
                bold=True,
            )
        )

    def run_failed(self, *, run_id: str, job_name: str, page_number: int | None, message: str) -> None:
        self._stop_spinner()
        location = f" page={page_number}" if page_number is not None else ""
        self._write_line(self._style(f"✗ run {run_id} failed at {job_name}{location}: {message}", "red", bold=True))

    def _render_status(self, message: str) -> None:
        if not self._tty:
            self._write_line(self._status_text(message))
            return
        line = self._status_text(message)
        width = max(40, get_terminal_size(fallback=(100, 20)).columns)
        if len(line) > width:
            line = line[: width - 1]
        pad = max(0, self._live_len - len(line))
        self.stream.write("\r" + line + (" " * pad))
        self.stream.flush()
        self._live_len = len(line)

    def _status_text(self, message: str) -> str:
        elapsed = max(monotonic() - self._started_at, 0.001)
        job_elapsed = max(monotonic() - self._job_started_at, 0.001)
        jobs_bar = self._progress_bar(self._jobs_done, self._total_jobs)
        overall_rate = self._jobs_done / elapsed if self._jobs_done else 0.0
        current_rows_rate = self._current_job_rows / job_elapsed if self._current_job_rows else 0.0
        eta = self._eta(elapsed, self._jobs_done, self._total_jobs)
        parts = [
            self._style("●", "cyan", bold=True),
            self._style(message, "white", bold=True),
            f"jobs {self._jobs_done}/{self._total_jobs}",
            jobs_bar,
            f"pages {self._total_pages}",
            f"rows {self._total_rows}",
            f"job p{self._current_job_pages} r{self._current_job_rows}",
        ]
        if self._current_job_name:
            parts.append(f"current {self._current_job_name} p{self._current_page}")
        if current_rows_rate:
            parts.append(f"{current_rows_rate:.0f} rows/s")
        if overall_rate:
            parts.append(f"{overall_rate:.2f} jobs/s")
        if eta:
            parts.append(f"ETA {eta}")
        return " | ".join(parts)

    def _spin(self) -> None:
        while not self._spinner_stop.wait(0.1):
            with self._spinner_lock:
                frame = self.SPINNER_FRAMES[self._spinner_frame % len(self.SPINNER_FRAMES)]
                self._spinner_frame += 1
                message = self._current_spinner_message
            self._render_status(f"{frame} {message}")

    def _stop_spinner(self) -> None:
        self._spinner_stop.set()
        thread = self._spinner_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.3)
        self._spinner_thread = None
        if self._tty and self._live_len:
            self.stream.write("\r" + (" " * self._live_len) + "\r")
            self.stream.flush()
            self._live_len = 0

    def _write_line(self, text: str) -> None:
        self._stop_spinner()
        print(text, file=self.stream, flush=True)

    def _progress_bar(self, done: int, total: int, width: int = 12) -> str:
        total = max(total, 1)
        filled = int(width * min(done, total) / total)
        empty = width - filled
        return self._style("[" + ("█" * filled) + ("░" * empty) + "]", "cyan")

    def _format_duration(self, seconds: float) -> str:
        seconds = max(0, int(round(seconds)))
        minutes, secs = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {minutes:02d}m {secs:02d}s"
        if minutes:
            return f"{minutes}m {secs:02d}s"
        return f"{secs}s"

    def _eta(self, elapsed: float, done: int, total: int | None) -> str | None:
        if not total or done <= 0:
            return None
        remaining = max(total - done, 0)
        if remaining == 0:
            return None
        eta_seconds = elapsed * remaining / done
        return self._format_duration(eta_seconds)

    def _style(self, text: str, color: str, *, bold: bool = False) -> str:
        if not self._color:
            return text
        colors = {
            "red": "31",
            "green": "32",
            "yellow": "33",
            "blue": "34",
            "magenta": "35",
            "cyan": "36",
            "white": "37",
        }
        prefix = ["1"] if bold else []
        prefix.append(colors.get(color, "37"))
        return f"\033[{';'.join(prefix)}m{text}\033[0m"
