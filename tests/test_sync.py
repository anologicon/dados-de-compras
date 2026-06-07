from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from compras_crawler.client import PageData
from compras_crawler.manifest import EndpointJob
from compras_crawler.sync import SyncConfig, SyncRunner


@dataclass
class FakeClient:
    pages_by_job: dict[str, list[PageData]]

    def iter_pages(self, path, params, accept="json", job_name=None):
        for page in self.pages_by_job[job_name]:
            yield page


def test_sync_runner_lands_and_publishes_rows(tmp_path: Path):
    db_path = tmp_path / "compras.duckdb"
    job = EndpointJob(
        name="uasg_status_true",
        operation_id="consultarUasg",
        path="/modulo-uasg/1_consultarUasg",
        entity_name="uasg",
        key_fields=("codigoUasg", "codigo_uasg"),
        base_params={"statusUasg": True},
    )
    client = FakeClient(
        pages_by_job={
            "uasg_status_true": [
                PageData(
                    url="https://dadosabertos.compras.gov.br/modulo-uasg/1_consultarUasg",
                    page_number=1,
                    params={"pagina": 1, "statusUasg": True, "_job_name": "uasg_status_true"},
                    records=[{"codigoUasg": 1, "nomeUasg": "A"}],
                    raw={"resultado": [{"codigoUasg": 1, "nomeUasg": "A"}], "paginasRestantes": 0},
                    content_type="application/json",
                    status_code=200,
                )
            ]
        }
    )
    runner = SyncRunner(
        config=SyncConfig(db_path=db_path, base_url="https://dadosabertos.compras.gov.br", resume=True),
        client=client,
        jobs=(job,),
    )

    run_id = runner.run()

    assert run_id
    with runner.warehouse.connect() as con:
        assert con.execute("select count(*) from bronze_pages").fetchone()[0] == 1
        assert con.execute("select count(*) from silver_records").fetchone()[0] == 1
        assert con.execute("select status from ops_runs where run_id = ?", [run_id]).fetchone()[0] == "finished"
