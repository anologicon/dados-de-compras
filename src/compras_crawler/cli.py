from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv

from .log import configure_logging
from .manifest import build_operation_catalog, default_date_window
from .sync import SyncConfig, build_jobs_for_config, build_runner
from .ui import ConsoleUI, TerminalTUI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="compras-crawler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    menu_parser = subparsers.add_parser("menu", help="Open an interactive menu for sync options")
    menu_parser.add_argument("--dry-run", action="store_true", help="Only print the generated sync command")

    sync_parser = subparsers.add_parser("sync", help="Run the Compras.gov.br sync pipeline")
    sync_parser.add_argument("--db-path", type=Path, default=Path("compras.duckdb"), help="DuckDB file path for synced data")
    sync_parser.add_argument("--ops-db-path", type=Path, default=None, help="SQLite file path for operation metadata")
    sync_parser.add_argument("--base-url", default="https://dadosabertos.compras.gov.br", help="API base URL (must use https)")
    sync_parser.add_argument("--start-date", default=None, help="Historical start date (YYYY-MM-DD)")
    sync_parser.add_argument("--end-date", default=None, help="Historical end date (YYYY-MM-DD)")
    sync_parser.add_argument("--page-size", type=int, default=None, help="Optional server page size")
    sync_parser.add_argument("--async", dest="async_mode", action="store_true", help="Fetch pages concurrently while keeping DuckDB writes serial")
    sync_parser.add_argument("--concurrency", type=int, default=5, help="Maximum concurrent page fetches when --async is enabled")
    sync_parser.add_argument("--scope", default="historical", help="Sync scope label")
    sync_parser.add_argument("--state-uf", default=None, help="UF abbreviation to restrict supported jobs (for example, SP)")
    sync_parser.add_argument("--municipality-code", type=int, default=None, help="IBGE municipality code for city-specific purchase runs")
    sync_parser.add_argument("--source", "--purchase-source", dest="purchase_sources", action="append", default=[], help="Repeatable municipality purchase source (currently: pncp)")
    sync_parser.add_argument("--pncp-modalidade-code", type=int, action="append", default=[], help="Repeatable modality code for PNCP location-filtered runs")
    sync_parser.add_argument("--operation", action="append", default=[], metavar="OPERATION_ID", help="Sync one or more Swagger/OpenAPI operationIds; repeatable")
    sync_parser.add_argument("--endpoint", action="append", default=[], metavar="NAME", help=argparse.SUPPRESS)
    sync_parser.add_argument("--list-operations", action="store_true", help="List available Swagger-style operations and exit")
    sync_parser.add_argument("--list-endpoints", action="store_true", help=argparse.SUPPRESS)
    sync_parser.add_argument("--no-resume", action="store_true", help="Start jobs from page 1 instead of checkpoints")
    sync_parser.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Console log level")
    sync_parser.add_argument(
        "--ui",
        choices=["auto", "tui", "console", "none"],
        default="auto",
        help="Progress UI mode: auto uses the full-screen TUI on a TTY and console output otherwise",
    )
    sync_parser.add_argument("--tui", action="store_true", help="Force the full-screen terminal UI")
    sync_parser.add_argument("--no-ui", action="store_true", help="Disable progress UI output")
    sync_parser.add_argument("--resume", action="store_true", help=argparse.SUPPRESS)
    return parser


def build_reporter(args: Any):
    if args.tui and args.ui not in {"auto", "tui"}:
        raise ValueError("--tui cannot be combined with --ui console/none")
    if args.no_ui or args.ui == "none":
        return None
    mode = "tui" if args.tui else args.ui
    if mode == "console":
        return ConsoleUI()
    if mode == "tui":
        return TerminalTUI()
    if mode == "auto":
        return TerminalTUI() if sys.stdout.isatty() else ConsoleUI()
    raise ValueError(f"Unknown UI mode: {mode}")


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "menu":
        from .menu import InteractiveSyncMenu

        menu = InteractiveSyncMenu()
        sync_argv = menu.collect_sync_argv()
        if sync_argv is None:
            return 0
        command = ["compras-crawler", "sync", *sync_argv]
        print("\nComando equivalente:")
        print(f"  {shlex.join(command)}")
        if args.dry_run:
            return 0
        if not menu.confirm_run():
            return 0
        return main(["sync", *sync_argv])

    if args.command == "sync":
        configure_logging(args.log_level)
        start_date = args.start_date or default_date_window()[0]
        end_date = args.end_date or default_date_window()[1]
        selectors = tuple(args.operation) + tuple(args.endpoint)
        purchase_sources = tuple(args.purchase_sources)
        if purchase_sources and selectors:
            parser.error("--source/--purchase-source cannot be combined with --operation/--endpoint")
        try:
            config = SyncConfig(
                db_path=args.db_path,
                ops_db_path=args.ops_db_path,
                base_url=args.base_url,
                token=os.getenv("COMPRAS_GOV_TOKEN"),
                start_date=args.start_date,
                end_date=args.end_date,
                page_size=args.page_size,
                endpoints=selectors,
                resume=not args.no_resume,
                scope=args.scope,
                state_uf=args.state_uf,
                municipality_code=args.municipality_code,
                pncp_modalidade_codes=tuple(args.pncp_modalidade_code),
                purchase_sources=purchase_sources,
                async_mode=args.async_mode,
                concurrency=args.concurrency,
            )
        except ValueError as exc:
            parser.error(str(exc))
        if args.list_operations or args.list_endpoints:
            jobs = build_jobs_for_config(config)
            catalog = build_operation_catalog(jobs)
            for spec in catalog:
                print(f"{spec.operation_id}\t{spec.entity_name}\t{spec.path}\tjobs={','.join(spec.job_names)}")
            return 0
        try:
            reporter = build_reporter(args)
        except ValueError as exc:
            parser.error(str(exc))
        runner = build_runner(config, reporter=reporter)
        try:
            runner.run()
        finally:
            close = getattr(reporter, "close", None)
            if close:
                close()
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
