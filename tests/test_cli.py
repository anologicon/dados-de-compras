from __future__ import annotations

import builtins
from pathlib import Path

import duckdb
import pytest

import compras_crawler.cli as cli


class DummyRunner:
    def __init__(self):
        self.ran = False

    def run(self):
        self.ran = True
        return "run-1"


def test_mcp_command_explains_missing_optional_dependency(monkeypatch, capsys):
    original_import = builtins.__import__

    def without_mcp(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise ModuleNotFoundError("No module named 'mcp'", name="mcp")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_mcp)
    with pytest.raises(SystemExit) as exc:
        cli.main(["mcp"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert 'pip install -e ".[mcp]"' in captured.err
    assert captured.out == ""


def test_cli_sync_invokes_runner(monkeypatch, tmp_path: Path):
    dummy = DummyRunner()
    captured = {}
    monkeypatch.setenv("COMPRAS_GOV_TOKEN", "abc")

    def fake_build_runner(config, reporter=None):
        captured["reporter"] = reporter
        captured["config"] = config
        return dummy

    monkeypatch.setattr(cli, "build_runner", fake_build_runner)

    exit_code = cli.main([
        "sync",
        "--db-path",
        str(tmp_path / "compras.duckdb"),
        "--operation",
        "consultarContratacoes_PNCP_14133",
        "--state-uf",
        "SP",
        "--municipality-code",
        "3550308",
        "--pncp-modalidade-code",
        "8",
        "--pncp-modalidade-code",
        "10",
    ])

    assert exit_code == 0
    assert dummy.ran is True
    assert captured["reporter"] is not None
    assert captured["config"].token == "abc"
    assert captured["config"].ops_db_path == tmp_path / "ops" / "compras_ops.sqlite"
    assert captured["config"].bronze_db_path == tmp_path / "compras_bronze.duckdb"
    assert captured["config"].endpoints == ("consultarContratacoes_PNCP_14133",)
    assert captured["config"].state_uf == "SP"
    assert captured["config"].municipality_code == 3550308
    assert captured["config"].pncp_modalidade_codes == (8, 10)
    assert captured["config"].purchase_sources == ()


def test_cli_rate_limit_flags_are_passed_to_config(monkeypatch, tmp_path: Path):
    dummy = DummyRunner()
    captured = {}

    def fake_build_runner(config, reporter=None):
        captured["config"] = config
        return dummy

    monkeypatch.setattr(cli, "build_runner", fake_build_runner)

    exit_code = cli.main([
        "sync",
        "--db-path",
        str(tmp_path / "compras.duckdb"),
        "--operation",
        "consultarUasg",
        "--delay-seconds",
        "2.5",
        "--rate-limit-sleep-seconds",
        "120",
        "--request-timeout",
        "10",
        "--request-retries",
        "7",
    ])

    assert exit_code == 0
    assert dummy.ran is True
    assert captured["config"].delay_seconds == 2.5
    assert captured["config"].rate_limit_sleep_seconds == 120
    assert captured["config"].request_timeout == 10
    assert captured["config"].request_retries == 7


def test_cli_async_flags_are_passed_to_config(monkeypatch, tmp_path: Path):
    dummy = DummyRunner()
    captured = {}

    def fake_build_runner(config, reporter=None):
        captured["config"] = config
        return dummy

    monkeypatch.setattr(cli, "build_runner", fake_build_runner)

    exit_code = cli.main([
        "sync",
        "--db-path",
        str(tmp_path / "compras.duckdb"),
        "--operation",
        "consultarUasg",
        "--async",
        "--concurrency",
        "3",
    ])

    assert exit_code == 0
    assert dummy.ran is True
    assert captured["config"].async_mode is True
    assert captured["config"].concurrency == 3


def test_cli_accepts_explicit_bronze_db_path(monkeypatch, tmp_path: Path):
    dummy = DummyRunner()
    captured = {}

    def fake_build_runner(config, reporter=None):
        captured["config"] = config
        return dummy

    monkeypatch.setattr(cli, "build_runner", fake_build_runner)

    exit_code = cli.main([
        "sync",
        "--db-path",
        str(tmp_path / "base"),
        "--bronze-db-path",
        str(tmp_path / "raw.duckdb"),
        "--operation",
        "consultarUasg",
    ])

    assert exit_code == 0
    assert captured["config"].bronze_db_path == tmp_path / "raw.duckdb"
    assert captured["config"].ops_db_path == tmp_path / "ops" / "base_ops.sqlite"


def test_cli_loads_token_from_dotenv(monkeypatch, tmp_path: Path):
    dummy = DummyRunner()
    captured = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("COMPRAS_GOV_TOKEN", raising=False)
    (tmp_path / ".env").write_text("COMPRAS_GOV_TOKEN=from-dotenv\n", encoding="utf-8")

    def fake_build_runner(config, reporter=None):
        captured["config"] = config
        return dummy

    monkeypatch.setattr(cli, "build_runner", fake_build_runner)

    exit_code = cli.main(["sync", "--db-path", str(tmp_path / "compras.duckdb"), "--operation", "consultarUasg"])

    assert exit_code == 0
    assert captured["config"].ops_db_path == tmp_path / "ops" / "compras_ops.sqlite"
    assert captured["config"].bronze_db_path == tmp_path / "compras_bronze.duckdb"
    assert captured["config"].token == "from-dotenv"


def test_cli_ui_modes(monkeypatch, tmp_path: Path):
    dummy = DummyRunner()
    captured = {}

    def fake_build_runner(config, reporter=None):
        captured["reporter"] = reporter
        return dummy

    monkeypatch.setattr(cli, "build_runner", fake_build_runner)

    exit_code = cli.main([
        "sync",
        "--db-path",
        str(tmp_path / "compras.duckdb"),
        "--operation",
        "consultarUasg",
        "--ui",
        "console",
    ])

    assert exit_code == 0
    assert isinstance(captured["reporter"], cli.ConsoleUI)

    exit_code = cli.main([
        "sync",
        "--db-path",
        str(tmp_path / "compras.duckdb"),
        "--operation",
        "consultarUasg",
        "--ui",
        "tui",
    ])

    assert exit_code == 0
    assert isinstance(captured["reporter"], cli.TerminalTUI)

    exit_code = cli.main([
        "sync",
        "--db-path",
        str(tmp_path / "compras.duckdb"),
        "--operation",
        "consultarUasg",
        "--ui",
        "none",
    ])

    assert exit_code == 0
    assert captured["reporter"] is None


def test_cli_rejects_conflicting_ui_flags(tmp_path: Path):
    with pytest.raises(SystemExit):
        cli.main([
            "sync",
            "--db-path",
            str(tmp_path / "compras.duckdb"),
            "--operation",
            "consultarUasg",
            "--ui",
            "console",
            "--tui",
        ])


def test_cli_list_operations_outputs_catalog(capsys):
    exit_code = cli.main(["sync", "--list-operations"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "consultarUasg" in output
    assert "consultarLicitacao" in output


def test_cli_list_operations_includes_pncp_when_selected(capsys):
    exit_code = cli.main([
        "sync",
        "--list-operations",
        "--operation",
        "consultarContratacoes_PNCP_14133",
        "--pncp-modalidade-code",
        "8",
        "--state-uf",
        "SP",
    ])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "consultarContratacoes_PNCP_14133" in output
    assert "pncp_14133_8" in output


def test_cli_migrate_bronze_copies_legacy_bronze_pages(tmp_path: Path, capsys):
    source_db_path = tmp_path / "compras.duckdb"
    with duckdb.connect(str(source_db_path)) as con:
        con.execute("create table bronze_pages(run_id text, job_name text, entity_name text, page_number integer, request_params_json text, response_format text, http_status integer, payload_json text, payload_text text, payload_hash text, fetched_at timestamp)")
        con.execute("insert into bronze_pages values ('run-1', 'job-1', 'uasg', 1, '{}', 'json', 200, '{}', null, 'hash', current_timestamp)")

    exit_code = cli.main([
        "migrate-bronze",
        "--source-db-path",
        str(source_db_path),
        "--db-path",
        str(tmp_path / "dados_abertos_compras"),
    ])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Migração Bronze concluída" in output
    with duckdb.connect(str(tmp_path / "dados_abertos_compras_bronze.duckdb"), read_only=True) as con:
        assert con.execute("select count(*) from bronze_pages").fetchone()[0] == 1
    assert not (tmp_path / "dados_abertos_compras_silver.duckdb").exists()
    assert not (tmp_path / "dados_abertos_compras_gold.duckdb").exists()


def test_cli_rejects_unsafe_tokened_base_url(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("COMPRAS_GOV_TOKEN", "abc")
    with pytest.raises(SystemExit):
        cli.main([
            "sync",
            "--db-path",
            str(tmp_path / "compras.duckdb"),
            "--base-url",
            "https://example.com",
            "--operation",
            "consultarUasg",
        ])


def test_cli_full_city_invokes_full_city_crawler(monkeypatch, tmp_path: Path):
    from compras_crawler import full_city

    captured = {}

    def fake_run_full_city_crawl(config, reporter=None):
        captured["config"] = config
        return full_city.FullCityResult(
            run_id="run-full-city",
            bronze_db_path=config.bronze_db_path,
            ops_db_path=config.ops_db_path,
            stats={},
            errors=(),
        )

    monkeypatch.setenv("COMPRAS_GOV_TOKEN", "abc")
    monkeypatch.setattr(full_city, "run_full_city_crawl", fake_run_full_city_crawl)

    exit_code = cli.main([
        "full-city",
        "--db-path",
        str(tmp_path / "floripa"),
        "--start-date",
        "2026-01-01",
        "--end-date",
        "2026-12-31",
        "--state-uf",
        "SC",
        "--municipality-code",
        "4205407",
        "--max-purchases",
        "10",
        "--no-reference-catalogs",
    ])

    assert exit_code == 0
    assert captured["config"].token == "abc"
    assert captured["config"].bronze_db_path == tmp_path / "floripa_bronze.duckdb"
    assert captured["config"].ops_db_path == tmp_path / "ops" / "floripa_ops.sqlite"
    assert captured["config"].municipality_code == 4205407
    assert captured["config"].state_uf == "SC"
    assert captured["config"].max_purchases == 10
    assert captured["config"].include_reference_catalogs is False


def test_cli_commands_coexist_after_merge():
    parser = cli.build_parser()
    for command in ("web", "mcp", "menu", "sync", "migrate-bronze"):
        assert parser.parse_args([command]).command == command
    assert parser.parse_args(["web-import", "--source-db-path", "bronze.duckdb",
                              "--municipality-code", "4202909", "--city-name", "Brusque",
                              "--state-uf", "SC"]).command == "web-import"


def test_cli_full_city_loads_dotenv_without_exposing_token(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("COMPRAS_GOV_TOKEN", raising=False)
    (tmp_path / ".env").write_text("COMPRAS_GOV_TOKEN=full-city-dotenv-token\n", encoding="utf-8")
    assert cli.main(["full-city", "--start-date", "2026-01-01", "--end-date", "2026-01-31",
                     "--state-uf", "SC", "--municipality-code", "4202909", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "token configured: True" in output
    assert "full-city-dotenv-token" not in output


def test_cli_full_city_dry_run_does_not_call_api(monkeypatch, tmp_path: Path, capsys):
    from compras_crawler import full_city

    def fail_run_full_city_crawl(config, reporter=None):
        raise AssertionError("should not call API on dry-run")

    monkeypatch.setattr(full_city, "run_full_city_crawl", fail_run_full_city_crawl)

    exit_code = cli.main([
        "full-city",
        "--db-path",
        str(tmp_path / "floripa"),
        "--start-date",
        "2026-01-01",
        "--end-date",
        "2026-12-31",
        "--state-uf",
        "SC",
        "--municipality-code",
        "4205407",
        "--dry-run",
    ])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Full-city crawl plan" in output
    assert "4205407/SC" in output


def test_cli_uses_municipality_purchase_mode(monkeypatch, tmp_path: Path):
    dummy = DummyRunner()
    captured = {}
    monkeypatch.setenv("COMPRAS_GOV_TOKEN", "abc")

    def fake_build_runner(config, reporter=None):
        captured["config"] = config
        return dummy

    monkeypatch.setattr(cli, "build_runner", fake_build_runner)

    exit_code = cli.main([
        "sync",
        "--db-path",
        str(tmp_path / "compras.duckdb"),
        "--state-uf",
        "SC",
        "--municipality-code",
        "4202909",
        "--pncp-modalidade-code",
        "8",
    ])

    assert exit_code == 0
    assert dummy.ran is True
    assert captured["config"].municipality_code == 4202909
    assert captured["config"].state_uf == "SC"
    assert captured["config"].purchase_sources == ("pncp",)
    assert captured["config"].endpoints == ()
    assert captured["config"].pncp_modalidade_codes == (8,)


def test_cli_rejects_purchase_source_with_operation(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("COMPRAS_GOV_TOKEN", "abc")
    with pytest.raises(SystemExit):
        cli.main([
            "sync",
            "--db-path",
            str(tmp_path / "compras.duckdb"),
            "--state-uf",
            "SC",
            "--municipality-code",
            "4202909",
            "--source",
            "pncp",
            "--operation",
            "consultarUasg",
        ])
