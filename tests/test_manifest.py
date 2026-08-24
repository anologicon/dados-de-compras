from __future__ import annotations

import pytest

from compras_crawler.manifest import (
    build_historical_manifest,
    build_municipality_purchase_manifest,
    build_operation_catalog,
    default_date_window,
)


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


def test_build_historical_manifest_includes_full_material_catalog():
    jobs = build_historical_manifest("2024-01-01", "2024-01-31", endpoints=("consultarMaterialNaturezaDespesa", "consultarMaterialCaracteristicas"))

    assert [job.operation_id for job in jobs] == [
        "consultarMaterialNaturezaDespesa",
        "consultarMaterialNaturezaDespesa",
        "consultarMaterialCaracteristicas",
    ]
    assert jobs[0].key_fields == (("codigoPdm", "codigoNaturezaDespesa"),)
    assert jobs[2].key_fields == (("codigoItem", "codigoCaracteristica", "codigoValorCaracteristica", "numeroCaracteristica"),)


def test_build_historical_manifest_includes_pncp_city_job():
    jobs = build_historical_manifest(
        "2024-01-01",
        "2024-01-31",
        endpoints=("consultarContratacoes_PNCP_14133",),
        state_uf="SP",
        municipality_code=3550308,
        pncp_modalidade_codes=(8, 10),
    )

    assert [job.name for job in jobs] == ["pncp_14133_8", "pncp_14133_10"]
    assert jobs[0].base_params["unidadeOrgaoUfSigla"] == "SP"
    assert jobs[0].base_params["unidadeOrgaoCodigoIbge"] == 3550308
    assert jobs[0].base_params["codigoModalidade"] == 8
    assert jobs[1].base_params["codigoModalidade"] == 10


def test_build_municipality_purchase_manifest_builds_pncp_jobs():
    jobs = build_municipality_purchase_manifest(
        "2024-01-01",
        "2024-01-31",
        municipality_code=4202909,
        state_uf="sc",
        pncp_modalidade_codes=(3, 5),
    )

    assert [job.name for job in jobs] == ["pncp_14133_3", "pncp_14133_5"]
    assert jobs[0].base_params["unidadeOrgaoCodigoIbge"] == 4202909
    assert jobs[0].base_params["unidadeOrgaoUfSigla"] == "SC"
    assert jobs[0].base_params["dataPublicacaoPncpInicial"] == "2024-01-01"
    assert jobs[1].base_params["codigoModalidade"] == 5


def test_build_municipality_purchase_manifest_rejects_unknown_source():
    with pytest.raises(ValueError, match="Unknown municipality purchase source"):
        build_municipality_purchase_manifest(
            "2024-01-01",
            "2024-01-31",
            municipality_code=4202909,
            sources=("pncp", "legacy"),
            pncp_modalidade_code=3,
        )


def test_build_municipality_purchase_manifest_rejects_pncp_without_modality_code():
    with pytest.raises(ValueError, match="pncp source requires pncp_modalidade_code"):
        build_municipality_purchase_manifest("2024-01-01", "2024-01-31", municipality_code=4202909)


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
