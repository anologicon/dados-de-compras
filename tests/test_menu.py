from __future__ import annotations

import io

from compras_crawler.menu import InteractiveSyncMenu


def make_menu(inputs: list[str]) -> InteractiveSyncMenu:
    iterator = iter(inputs)
    return InteractiveSyncMenu(input_func=lambda: next(iterator), stream=io.StringIO())


def test_menu_can_build_list_operations_command():
    menu = make_menu(["2"])

    assert menu.collect_sync_argv() == ["--list-operations"]


def test_menu_builds_municipality_sync_command():
    menu = make_menu([
        "",  # default: configure and run sync
        "2",  # municipality flow
        "",  # default DuckDB path
        "",  # automatic ops DB path
        "",  # default base URL
        "2024-01-01",
        "2024-01-31",
        "100",
        "",  # default scope
        "SC",
        "4202909",
        "8,10",
        "n",  # do not resume
        "2",  # INFO
        "3",  # console UI
    ])

    argv = menu.collect_sync_argv()

    assert argv == [
        "--db-path",
        "compras.duckdb",
        "--base-url",
        "https://dadosabertos.compras.gov.br",
        "--start-date",
        "2024-01-01",
        "--end-date",
        "2024-01-31",
        "--page-size",
        "100",
        "--scope",
        "municipality-purchases",
        "--state-uf",
        "SC",
        "--municipality-code",
        "4202909",
        "--source",
        "pncp",
        "--pncp-modalidade-code",
        "8",
        "--pncp-modalidade-code",
        "10",
        "--no-resume",
        "--log-level",
        "INFO",
        "--ui",
        "console",
    ]


def test_menu_builds_historical_operation_command():
    menu = make_menu([
        "1",  # configure and run sync
        "1",  # historical flow
        "compras-test.duckdb",
        "",  # automatic ops DB path
        "",  # default base URL
        "2024-02-01",
        "2024-02-02",
        "",  # page size
        "teste",
        "SP",
        "consultarUasg,consultarLicitacao",
        "",  # resume
        "",  # WARNING
        "2",  # TUI
    ])

    argv = menu.collect_sync_argv()

    assert argv[:10] == [
        "--db-path",
        "compras-test.duckdb",
        "--base-url",
        "https://dadosabertos.compras.gov.br",
        "--start-date",
        "2024-02-01",
        "--end-date",
        "2024-02-02",
        "--scope",
        "teste",
    ]
    assert ["--state-uf", "SP"] == argv[10:12]
    assert ["--operation", "consultarUasg"] == argv[12:14]
    assert ["--operation", "consultarLicitacao"] == argv[14:16]
    assert argv[-4:] == ["--log-level", "WARNING", "--ui", "tui"]
