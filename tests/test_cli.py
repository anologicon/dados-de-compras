from __future__ import annotations

from pathlib import Path

import pytest

import compras_crawler.cli as cli


class DummyRunner:
    def __init__(self):
        self.ran = False

    def run(self):
        self.ran = True
        return "run-1"


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
    assert captured["config"].ops_db_path == tmp_path / "compras_ops.sqlite"
    assert captured["config"].endpoints == ("consultarContratacoes_PNCP_14133",)
    assert captured["config"].state_uf == "SP"
    assert captured["config"].municipality_code == 3550308
    assert captured["config"].pncp_modalidade_codes == (8, 10)
    assert captured["config"].purchase_sources == ()


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
    assert captured["config"].ops_db_path == tmp_path / "compras_ops.sqlite"
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
