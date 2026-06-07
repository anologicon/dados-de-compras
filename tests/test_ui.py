from __future__ import annotations

import io
from pathlib import Path

from compras_crawler.ui import ConsoleUI, RunContext


def test_console_ui_renders_run_summary():
    stream = io.StringIO()
    ui = ConsoleUI(stream=stream)

    ui.start(
        ctx=RunContext(
            run_id="run-1",
            db_path=Path("compras.duckdb"),
            base_url="https://dadosabertos.compras.gov.br",
            scope="historical",
            start_date="2024-01-01",
            end_date="2024-01-02",
            page_size=1,
            resume=True,
            total_jobs=2,
        )
    )
    ui.job_started(index=1, total=2, job_name="uasg_true", entity_name="uasg", path="/x", start_page=1, resume=True)
    ui.page_done(job_name="uasg_true", page_number=1, status_code=200, record_count=10)
    ui.job_finished(job_name="uasg_true", next_page=2)
    ui.run_finished(run_id="run-1", status="finished")

    output = stream.getvalue()
    assert "compras-crawler sync" in output
    assert "run id:   run-1" in output
    assert "▶ [1/2] uasg_true (uasg)" in output
    assert "✓ [1] uasg_true done" in output
    assert "FINISHED: run run-1" in output
