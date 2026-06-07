from __future__ import annotations

import pytest

from compras_crawler.manifest import build_historical_manifest, build_operation_catalog, default_date_window


def test_build_historical_manifest_filters_endpoints():
    jobs = build_historical_manifest("2024-01-01", "2024-01-31", endpoints=("consultarUasg", "consultarLicitacao"))

    assert [job.name for job in jobs] == ["uasg_true", "uasg_false", "licitacao"]


def test_build_historical_manifest_applies_state_filter_to_uasg():
    jobs = build_historical_manifest("2024-01-01", "2024-01-31", state_uf="SP", endpoints=("consultarUasg",))

    assert all(job.base_params["siglaUf"] == "SP" for job in jobs)


def test_build_operation_catalog_groups_jobs():
    jobs = build_historical_manifest("2024-01-01", "2024-01-31")
    catalog = build_operation_catalog(jobs)

    assert catalog[0].operation_id == "consultarUasg"
    assert catalog[0].job_names == ("uasg_true", "uasg_false")


def test_build_historical_manifest_includes_pncp_city_job():
    jobs = build_historical_manifest(
        "2024-01-01",
        "2024-01-31",
        endpoints=("consultarContratacoes_PNCP_14133",),
        state_uf="SP",
        municipality_code=3550308,
        pncp_modalidade_code=8,
    )

    assert [job.name for job in jobs] == ["pncp_14133"]
    assert jobs[0].base_params["unidadeOrgaoUfSigla"] == "SP"
    assert jobs[0].base_params["unidadeOrgaoCodigoIbge"] == 3550308
    assert jobs[0].base_params["codigoModalidade"] == 8


def test_default_date_window_returns_yesterday(monkeypatch):
    from datetime import date

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 7)

    monkeypatch.setattr("compras_crawler.manifest.date", FrozenDate)

    assert default_date_window() == ("2026-06-06", "2026-06-06")


def test_build_historical_manifest_rejects_unknown_endpoint():
    with pytest.raises(ValueError, match="No endpoints matched"):
        build_historical_manifest("2024-01-01", "2024-01-31", endpoints=("does-not-exist",))


def test_build_historical_manifest_rejects_pncp_without_modalidade_code():
    with pytest.raises(ValueError, match="pncp_modalidade_code"):
        build_historical_manifest("2024-01-01", "2024-01-31", endpoints=("consultarContratacoes_PNCP_14133",))
