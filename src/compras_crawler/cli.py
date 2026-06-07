from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from .log import configure_logging
from .manifest import build_historical_manifest, build_operation_catalog, default_date_window
from .sync import SyncConfig, build_runner
from .ui import ConsoleUI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="compras-crawler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="Run the Compras.gov.br sync pipeline")
    sync_parser.add_argument("--db-path", type=Path, default=Path("compras.duckdb"), help="DuckDB file path")
    sync_parser.add_argument("--base-url", default="https://dadosabertos.compras.gov.br", help="API base URL (must use https)")
    sync_parser.add_argument("--start-date", default=None, help="Historical start date (YYYY-MM-DD)")
    sync_parser.add_argument("--end-date", default=None, help="Historical end date (YYYY-MM-DD)")
    sync_parser.add_argument("--page-size", type=int, default=None, help="Optional server page size")
    sync_parser.add_argument("--scope", default="historical", help="Sync scope label")
    sync_parser.add_argument("--state-uf", default=None, help="UF abbreviation to restrict supported jobs (for example, SP)")
    sync_parser.add_argument("--municipality-code", type=int, default=None, help="IBGE municipality code for city-specific PNCP runs")
    sync_parser.add_argument("--pncp-modalidade-code", type=int, default=None, help="Required modality code for PNCP location-filtered runs")
    sync_parser.add_argument("--operation", action="append", default=[], metavar="OPERATION_ID", help="Sync one or more Swagger/OpenAPI operationIds; repeatable")
    sync_parser.add_argument("--endpoint", action="append", default=[], metavar="NAME", help=argparse.SUPPRESS)
    sync_parser.add_argument("--list-operations", action="store_true", help="List available Swagger-style operations and exit")
    sync_parser.add_argument("--list-endpoints", action="store_true", help=argparse.SUPPRESS)
    sync_parser.add_argument("--no-resume", action="store_true", help="Start jobs from page 1 instead of checkpoints")
    sync_parser.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Console log level")
    sync_parser.add_argument("--no-ui", action="store_true", help="Disable the friendly console UI")
    sync_parser.add_argument("--resume", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "sync":
        configure_logging(args.log_level)
        start_date = args.start_date or default_date_window()[0]
        end_date = args.end_date or default_date_window()[1]
        selectors = tuple(args.operation) + tuple(args.endpoint)
        try:
            config = SyncConfig(
                db_path=args.db_path,
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
                pncp_modalidade_code=args.pncp_modalidade_code,
            )
        except ValueError as exc:
            parser.error(str(exc))
        if args.list_operations or args.list_endpoints:
            jobs = build_historical_manifest(
                start_date,
                end_date,
                page_size=config.page_size,
                endpoints=config.endpoints or None,
                state_uf=config.state_uf,
                municipality_code=config.municipality_code,
                pncp_modalidade_code=config.pncp_modalidade_code,
            )
            catalog = build_operation_catalog(jobs)
            for spec in catalog:
                print(f"{spec.operation_id}\t{spec.entity_name}\t{spec.path}\tjobs={','.join(spec.job_names)}")
            return 0
        reporter = None if args.no_ui else ConsoleUI()
        runner = build_runner(config, reporter=reporter)
        runner.run()
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
