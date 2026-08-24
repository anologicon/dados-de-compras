from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from shutil import get_terminal_size
from time import monotonic
from typing import TextIO
import sys
import threading


@dataclass(frozen=True)
class RunContext:
    run_id: str
    db_path: Path
    ops_db_path: Path
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
        self._write_line(f"data db:  {ctx.db_path}")
        self._write_line(f"ops db:   {ctx.ops_db_path}")
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

    def close(self) -> None:
        self._stop_spinner()


class TerminalTUI:
    """Full-screen ANSI terminal UI for sync progress.

    The class intentionally avoids external dependencies.  When stdout is not a
    TTY it delegates to ConsoleUI, so it is safe to request from CI, tests, or a
    redirected terminal.
    """

    SPINNER_FRAMES = ConsoleUI.SPINNER_FRAMES

    def __init__(self, stream: TextIO | None = None, *, color: bool | None = None, refresh_interval: float = 0.1):
        self.stream = stream or sys.stdout
        self._tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self._color = self._tty if color is None else color
        self._fallback = None if self._tty else ConsoleUI(stream=self.stream, color=color)
        self._refresh_interval = refresh_interval
        self._lock = threading.RLock()
        self._render_stop = threading.Event()
        self._render_thread: threading.Thread | None = None
        self._active = False
        self._started_at = monotonic()
        self._job_started_at = monotonic()
        self._ctx: RunContext | None = None
        self._run_id = ""
        self._scope = ""
        self._status = "idle"
        self._phase = "waiting"
        self._total_jobs = 1
        self._jobs_done = 0
        self._total_pages = 0
        self._total_rows = 0
        self._current_job_index = 0
        self._current_job_total = 0
        self._current_job_name = ""
        self._current_entity_name = ""
        self._current_path = ""
        self._current_page = 0
        self._current_job_pages = 0
        self._current_job_rows = 0
        self._last_http = ""
        self._failure = ""
        self._spinner_frame = 0
        self._events: deque[str] = deque(maxlen=10)

    def start(self, *, ctx: RunContext) -> None:
        if self._delegate("start", ctx=ctx):
            return
        with self._lock:
            self._ctx = ctx
            self._run_id = ctx.run_id
            self._scope = ctx.scope
            self._status = "preparando execução"
            self._phase = "starting"
            self._started_at = monotonic()
            self._job_started_at = self._started_at
            self._total_jobs = max(ctx.total_jobs, 1)
            self._jobs_done = 0
            self._total_pages = 0
            self._total_rows = 0
            self._current_job_index = 0
            self._current_job_total = ctx.total_jobs
            self._current_job_name = ""
            self._current_entity_name = ""
            self._current_path = ""
            self._current_page = 0
            self._current_job_pages = 0
            self._current_job_rows = 0
            self._last_http = ""
            self._failure = ""
            self._events.clear()
            self._add_event_unlocked(f"run {ctx.run_id} iniciado")
        self._activate()
        self._start_render_thread()
        self._render()

    def job_started(self, *, index: int, total: int, job_name: str, entity_name: str, path: str, start_page: int, resume: bool) -> None:
        if self._delegate(
            "job_started",
            index=index,
            total=total,
            job_name=job_name,
            entity_name=entity_name,
            path=path,
            start_page=start_page,
            resume=resume,
        ):
            return
        with self._lock:
            self._current_job_index = index
            self._current_job_total = total
            self._current_job_name = job_name
            self._current_entity_name = entity_name
            self._current_path = path
            self._current_page = start_page
            self._current_job_pages = 0
            self._current_job_rows = 0
            self._job_started_at = monotonic()
            suffix = " retomado" if resume else ""
            self._status = f"job {index}/{total}{suffix}"
            self._phase = "job"
            self._last_http = ""
            self._add_event_unlocked(f"▶ {job_name} ({entity_name}) página inicial {start_page}")
        self._render()

    def fetch_started(self, *, job_name: str, page_number: int, path: str) -> None:
        if self._delegate("fetch_started", job_name=job_name, page_number=page_number, path=path):
            return
        with self._lock:
            self._current_page = page_number
            self._status = f"buscando {job_name} página {page_number}"
            self._phase = "fetching"
        self._render()

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
        if self._delegate(
            "fetch_finished",
            job_name=job_name,
            page_number=page_number,
            status_code=status_code,
            elapsed_seconds=elapsed_seconds,
            record_count=record_count,
            content_type=content_type,
        ):
            return
        with self._lock:
            self._last_http = f"HTTP {status_code} · {record_count} rows · {self._format_duration(elapsed_seconds)} · {content_type}"
            self._status = f"página {page_number} recebida"
            self._phase = "persisting"
            self._add_event_unlocked(f"✓ {job_name} p{page_number}: {record_count} rows em {self._format_duration(elapsed_seconds)}")
        self._render()

    def page_done(self, *, job_name: str, page_number: int, status_code: int, record_count: int) -> None:
        if self._delegate("page_done", job_name=job_name, page_number=page_number, status_code=status_code, record_count=record_count):
            return
        with self._lock:
            self._total_pages += 1
            self._total_rows += record_count
            self._current_job_pages += 1
            self._current_job_rows += record_count
            self._current_page = page_number + 1
            self._status = f"{job_name} p{page_number} persistida"
            self._phase = "job"
        self._render()

    def job_finished(self, *, job_name: str, next_page: int) -> None:
        if self._delegate("job_finished", job_name=job_name, next_page=next_page):
            return
        with self._lock:
            elapsed = monotonic() - self._job_started_at
            self._jobs_done += 1
            self._status = f"{job_name} concluído"
            self._phase = "waiting"
            self._add_event_unlocked(
                f"✓ {job_name} concluído: {self._current_job_pages} páginas, {self._current_job_rows} rows, próxima p{next_page}, {self._format_duration(elapsed)}"
            )
        self._render()

    def run_finished(self, *, run_id: str, status: str) -> None:
        if self._delegate("run_finished", run_id=run_id, status=status):
            return
        with self._lock:
            elapsed = monotonic() - self._started_at
            self._status = status
            self._phase = "finished" if status == "finished" else "failed"
            self._add_event_unlocked(f"{status.upper()}: run {run_id} em {self._format_duration(elapsed)}")
            summary = self._summary_line(run_id=run_id, status=status, elapsed=elapsed)
        self._finish_screen(summary, ok=status == "finished")

    def run_failed(self, *, run_id: str, job_name: str, page_number: int | None, message: str) -> None:
        if self._delegate("run_failed", run_id=run_id, job_name=job_name, page_number=page_number, message=message):
            return
        with self._lock:
            elapsed = monotonic() - self._started_at
            location = f" página {page_number}" if page_number is not None else ""
            self._status = "failed"
            self._phase = "failed"
            self._failure = f"{job_name}{location}: {message}"
            self._add_event_unlocked(f"✗ falha em {self._failure}")
            summary = self._summary_line(run_id=run_id, status="failed", elapsed=elapsed)
        self._finish_screen(summary, ok=False)

    def close(self) -> None:
        if self._fallback:
            close = getattr(self._fallback, "close", None)
            if close:
                close()
            return
        self._stop_render_thread()
        self._deactivate()

    def _delegate(self, method_name: str, **kwargs) -> bool:
        if not self._fallback:
            return False
        getattr(self._fallback, method_name)(**kwargs)
        return True

    def _activate(self) -> None:
        if self._active:
            return
        self.stream.write("\033[?1049h\033[?25l\033[2J\033[H")
        self.stream.flush()
        self._active = True

    def _deactivate(self) -> None:
        if not self._active:
            return
        self.stream.write("\033[?25h\033[?1049l")
        self.stream.flush()
        self._active = False

    def _start_render_thread(self) -> None:
        if self._render_thread and self._render_thread.is_alive():
            return
        self._render_stop.clear()
        self._render_thread = threading.Thread(target=self._render_loop, daemon=True)
        self._render_thread.start()

    def _stop_render_thread(self) -> None:
        self._render_stop.set()
        thread = self._render_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.5)
        self._render_thread = None

    def _render_loop(self) -> None:
        while not self._render_stop.wait(self._refresh_interval):
            with self._lock:
                self._spinner_frame += 1
            self._render()

    def _render(self) -> None:
        if not self._active:
            return
        with self._lock:
            width, height = get_terminal_size(fallback=(100, 30))
            width = max(20, width)
            height = max(8, height)
            ctx = self._ctx
            elapsed = monotonic() - self._started_at
            job_elapsed = monotonic() - self._job_started_at
            frame = self.SPINNER_FRAMES[self._spinner_frame % len(self.SPINNER_FRAMES)]
            spinner = frame if self._phase in {"starting", "fetching", "persisting", "job", "waiting"} else " "
            jobs_bar = self._progress_bar(self._jobs_done, self._total_jobs, width=24)
            rows_rate = self._current_job_rows / job_elapsed if self._current_job_rows and job_elapsed > 0 else 0.0
            eta = self._eta(elapsed, self._jobs_done, self._total_jobs)
            body = [
                "",
                "RUN",
                f"  id:        {self._run_id or '-'}",
                f"  scope:     {self._scope or '-'}",
                f"  elapsed:   {self._format_duration(elapsed)}" + (f" · ETA {eta}" if eta else ""),
            ]
            if ctx:
                date_window = "-"
                if ctx.start_date or ctx.end_date:
                    date_window = f"{ctx.start_date or '-'} → {ctx.end_date or '-'}"
                body.extend(
                    [
                        f"  data db:   {ctx.db_path}",
                        f"  ops db:    {ctx.ops_db_path}",
                        f"  base url:  {ctx.base_url}",
                        f"  date:      {date_window}",
                        f"  page size: {ctx.page_size if ctx.page_size is not None else '-'} · resume: {'yes' if ctx.resume else 'no'}",
                    ]
                )
            body.extend(
                [
                    "",
                    "PROGRESSO",
                    f"  jobs:  {jobs_bar} {self._jobs_done}/{self._total_jobs}",
                    f"  pages: {self._total_pages} · rows: {self._total_rows}",
                    "",
                    "JOB ATUAL",
                    f"  {spinner} status: {self._status}",
                    f"  job:    {self._current_job_index}/{self._current_job_total or self._total_jobs} {self._current_job_name or '-'}",
                    f"  entity: {self._current_entity_name or '-'}",
                    f"  path:   {self._current_path or '-'}",
                    f"  page:   {self._current_page or '-'} · job pages: {self._current_job_pages} · job rows: {self._current_job_rows}",
                ]
            )
            if rows_rate:
                body.append(f"  rate:   {rows_rate:.0f} rows/s")
            if self._last_http:
                body.append(f"  last:   {self._last_http}")
            if self._failure:
                body.extend(["", "FALHA", f"  {self._failure}"])
            body.extend(["", "EVENTOS"])
            if self._events:
                body.extend(f"  {event}" for event in list(self._events)[-8:])
            else:
                body.append("  sem eventos ainda")
            footer = "Ctrl-C aborta · --ui console volta ao modo clássico · --no-ui desliga a UI"
        header = self._style(" compras-crawler TUI ".ljust(width), "cyan", bold=True, reverse=True)
        footer_line = self._style(self._fit(footer, width), "white", reverse=True)
        rows = [header]
        body_slots = height - 2
        rows.extend(self._fit(line, width) for line in body[:body_slots])
        rows.extend("" for _ in range(max(0, body_slots - len(body))))
        rows.append(footer_line)
        self.stream.write("\033[H" + "\n".join(row + "\033[K" for row in rows[:height]))
        self.stream.flush()

    def _finish_screen(self, summary: str, *, ok: bool) -> None:
        self._stop_render_thread()
        self._render()
        self._deactivate()
        color = "green" if ok else "red"
        print(self._style(summary, color, bold=True), file=self.stream, flush=True)

    def _add_event_unlocked(self, message: str) -> None:
        elapsed = self._format_duration(monotonic() - self._started_at)
        self._events.append(f"{elapsed:>8}  {message}")

    def _summary_line(self, *, run_id: str, status: str, elapsed: float) -> str:
        return (
            f"{status.upper()}: run {run_id} | jobs={self._jobs_done} | pages={self._total_pages} | "
            f"rows={self._total_rows} | {self._format_duration(elapsed)}"
        )

    def _progress_bar(self, done: int, total: int, width: int = 24) -> str:
        total = max(total, 1)
        done = min(max(done, 0), total)
        filled = int(width * done / total)
        pct = int(100 * done / total)
        return "[" + ("█" * filled) + ("░" * (width - filled)) + f"] {pct:3d}%"

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
        return self._format_duration(elapsed * remaining / done)

    def _fit(self, text: str, width: int) -> str:
        if len(text) <= width:
            return text
        if width <= 1:
            return text[:width]
        return text[: width - 1] + "…"

    def _style(self, text: str, color: str, *, bold: bool = False, reverse: bool = False) -> str:
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
        prefix: list[str] = []
        if bold:
            prefix.append("1")
        if reverse:
            prefix.append("7")
        prefix.append(colors.get(color, "37"))
        return f"\033[{';'.join(prefix)}m{text}\033[0m"
