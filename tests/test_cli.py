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
    ])

    assert exit_code == 0
    assert dummy.ran is True
    assert captured["reporter"] is not None
    assert captured["config"].token == "abc"
    assert captured["config"].endpoints == ("consultarContratacoes_PNCP_14133",)
    assert captured["config"].state_uf == "SP"
    assert captured["config"].municipality_code == 3550308
    assert captured["config"].pncp_modalidade_code == 8


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
    assert captured["config"].token == "from-dotenv"


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
    assert "pncp_14133" in output


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


def test_cli_rejects_city_filter_without_pncp_operation(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("COMPRAS_GOV_TOKEN", "abc")
    with pytest.raises(SystemExit):
        cli.main([
            "sync",
            "--db-path",
            str(tmp_path / "compras.duckdb"),
            "--state-uf",
            "SP",
            "--municipality-code",
            "3550308",
            "--pncp-modalidade-code",
            "8",
        ])
