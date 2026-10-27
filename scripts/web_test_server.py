"""Deterministic browser-test server; no scheduler, credentials, or real API calls."""
from tempfile import TemporaryDirectory

import uvicorn

from compras_crawler.normalize import stable_hash, stable_json
from compras_crawler.storage import BronzeWarehouse
from compras_crawler.web.analytics import build_snapshot
from compras_crawler.web.app import create_app
from compras_crawler.web.store import AppStore


def main():
    with TemporaryDirectory(prefix="compras-web-e2e-") as root:
        store = AppStore(root)
        store.init_schema()
        store.add_city("4202909", "Brusque", "SC")
        warehouse = BronzeWarehouse(store.city_dir("4202909") / "bronze.duckdb")
        warehouse.init_schema()
        payload = {"resultado": [dict(
            idCompra="teste-001", numeroControlePNCP="pncp-teste-001", unidadeOrgaoCodigoIbge=4202909,
            dataPublicacaoPncp="2026-01-15", objetoCompra="Aquisição de material hospitalar",
            orgaoEntidadeRazaoSocial="Órgão de teste de Brusque", modalidadeNome="Pregão eletrônico",
            valorTotalEstimado=10000, valorTotalHomologado=8500,
        )], "totalPaginas": 1}
        warehouse.land_page(run_id="fixture", job_name="pncp_test", entity_name="pncp_contratacao", page_number=1,
                            request_params_json="{}", response_format="json", http_status=200,
                            payload_json=stable_json(payload), payload_text=None, payload_hash=stable_hash(payload))
        # Connected-explorer fixtures, all synthetic and local. Enough items and
        # results for real pagination, plus missing and conflicting references.
        def related(entity, records):
            page = {"resultado": records, "totalPaginas": 1}
            warehouse.land_page(run_id="connected-fixture", job_name=entity, entity_name=entity, page_number=1,
                                request_params_json="{}", response_format="json", http_status=200,
                                payload_json=stable_json(page), payload_text=None, payload_hash=stable_hash(page))

        items = [dict(idCompra="teste-001", numeroControlePNCPCompra="pncp-teste-001", idCompraItem=f"teste-item-{i}",
                      numeroItemPncp=i, descricaoResumida="Luva hospitalar" if i == 1 else f"Material hospitalar {i}",
                      quantidade=0 if i == 1 else None, valorUnitarioEstimado=0 if i == 1 else None,
                      codItemCatalogo=1000 + i, materialOuServico="M", unidadeMedida="Unidade") for i in range(1, 25)]
        items.append(dict(items[0], idCompraItem="conflicting-item", numeroItemPncp=25,
                          numeroControlePNCPCompra="outra-compra", descricaoResumida="Item com identificadores conflitantes"))
        related("pncp_item_contratacao", items)
        awards = [dict(idCompra="teste-001", numeroControlePNCPCompra="pncp-teste-001", idCompraItem="teste-item-1",
                       numeroItemPncp=1, sequencialResultado=i, niFornecedor="12345678000199", tipoPessoa="PJ",
                       nomeRazaoSocialFornecedor="Fornecedor hospitalar de teste", quantidadeHomologada=i - 1,
                       valorUnitarioHomologado=0 if i == 1 else 8.5, valorTotalHomologado=0 if i == 1 else (i - 1) * 8.5,
                       situacaoCompraItemResultadoNome="Informado") for i in range(1, 23)]
        awards.extend([
            dict(awards[0], sequencialResultado=23, niFornecedor="01234567890", tipoPessoa="PF",
                 nomeRazaoSocialFornecedor="Pessoa de teste", situacaoCompraItemResultadoNome="Cancelado", dataCancelamentoPncp="2026-01-20"),
            dict(awards[0], idCompraItem="teste-item-2", numeroItemPncp=2, niFornecedor="22222222000122",
                 nomeRazaoSocialFornecedor="Fornecedor sem cadastro"),
            dict(awards[0], idCompraItem="item-nao-coletado", numeroItemPncp=99),
            dict(awards[0], sequencialResultado=24, numeroControlePNCPCompra="outra-compra"),
        ])
        related("pncp_resultado_item", awards)
        related("fornecedor", [dict(cnpj="12.345.678/0001-99", nomeRazaoSocialFornecedor="Fornecedor no cadastro local",
                                    nomeCnae="Comércio de materiais hospitalares", porteEmpresaNome="Microempresa",
                                    nomeMunicipio="Município de referência", ufSigla="SC", ativo=True, habilitadoLicitar=False),
                               dict(cpf="01234567890", nomeRazaoSocialFornecedor="Pessoa no cadastro local", ativo=True)])
        build_snapshot(store, "4202909")
        # A richer, separate municipality exercises multiple years, missing/zero
        # amounts, long rankings and more than five modalities without changing
        # the original one-purchase fixture used by navigation tests.
        store.add_city("4216602", "São José", "SC")
        rich = BronzeWarehouse(store.city_dir("4216602") / "bronze.duckdb")
        rich.init_schema()
        records = []
        for i in range(12):
            month = (i + 10) % 12 + 1
            year = 2025 if i < 2 else 2026
            record = dict(
                idCompra=f"rich-{i}", unidadeOrgaoCodigoIbge=4216602,
                dataPublicacaoPncp=f"{year}-{month:02d}-15", objetoCompra=f"Compra sintética {i}",
                orgaoEntidadeRazaoSocial=f"Órgão de teste {i + 1:02d}" if i < 11 else "Z - Órgão de maior valor",
                modalidadeNome=f"Modalidade {i % 7 + 1}",
                valorTotalEstimado=None if i == 4 else 0 if i == 2 else (i + 1) * 1000,
                valorTotalHomologado=None if i in (0, 4, 6) else 0 if i == 1 else 900000 if i == 11 else 500,
            )
            records.append(record)
            if i < 8:
                records.append(dict(record, idCompra=f"rich-extra-{i}"))
        rich_payload = {"resultado": records, "totalPaginas": 1}
        rich.land_page(run_id="rich-fixture", job_name="pncp_test", entity_name="pncp_contratacao", page_number=1,
                       request_params_json="{}", response_format="json", http_status=200,
                       payload_json=stable_json(rich_payload), payload_text=None, payload_hash=stable_hash(rich_payload))
        build_snapshot(store, "4216602")
        app = create_app(root, port=8765, start_workers=False)
        # All IBGE reads/refreshes stay deterministic and offline in browser tests.
        app.state.catalog._download = lambda: [
            {"id": 4202909, "nome": "Brusque"}, {"id": 4205407, "nome": "Florianópolis"},
            {"id": 4216602, "nome": "São José"}, {"id": 3549904, "nome": "São José dos Campos"},
        ]
        app.state.catalog.init_schema()
        app.state.catalog.ensure()
        uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False)


if __name__ == "__main__":
    main()
