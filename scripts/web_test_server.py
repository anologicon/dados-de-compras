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
        build_snapshot(store, "4202909")
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
