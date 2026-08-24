from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from compras_crawler.client import PageData
from compras_crawler.manifest import EndpointJob
from compras_crawler.sync import AsyncSyncRunner, SyncConfig, SyncRunner, build_jobs_for_config, build_runner


@dataclass
class FakeClient:
    pages_by_job: dict[str, list[PageData]]

    def iter_pages(self, path, params, accept="json", job_name=None):
        for page in self.pages_by_job[job_name]:
            yield page


class FakeAsyncClient:
    def __init__(self, pages_by_number: dict[int, PageData]):
        self.pages_by_number = pages_by_number
        self.calls: list[int] = []

    async def fetch_page(self, path, params, accept="json"):
        page_number = int(params["pagina"])
        self.calls.append(page_number)
        return self.pages_by_number[page_number]


def test_build_jobs_for_config_uses_municipality_purchase_manifest(tmp_path: Path):
    config = SyncConfig(
        db_path=tmp_path / "compras.duckdb",
        ops_db_path=tmp_path / "compras_ops.sqlite",
        base_url="https://dadosabertos.compras.gov.br",
        municipality_code=4202909,
        state_uf="SC",
        pncp_modalidade_codes=(8,),
    )

    jobs = build_jobs_for_config(config)

    assert [job.name for job in jobs] == ["pncp_14133_8"]
    assert jobs[0].base_params["unidadeOrgaoCodigoIbge"] == 4202909
    assert config.purchase_sources == ("pncp",)
    assert config.bronze_db_path == tmp_path / "compras_bronze.duckdb"


def test_sync_runner_lands_bronze_pages_only(tmp_path: Path):
    base_db_path = tmp_path / "compras.duckdb"
    ops_db_path = tmp_path / "compras_ops.sqlite"
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
        config=SyncConfig(db_path=base_db_path, ops_db_path=ops_db_path, base_url="https://dadosabertos.compras.gov.br", resume=True),
        client=client,
        jobs=(job,),
    )

    run_id = runner.run()

    assert run_id
    with runner.warehouse.connect() as con:
        assert con.execute("select count(*) from bronze_pages").fetchone()[0] == 1
        tables = {row[0] for row in con.execute("select table_name from duckdb_tables()").fetchall()}
        assert tables == {"bronze_pages"}
    with runner.ops_store.connect() as con:
        row = con.execute("select status, bronze_db_path from ops_runs where run_id = ?", [run_id]).fetchone()
        assert row == ("finished", str(tmp_path / "compras_bronze.duckdb"))


def test_build_runner_uses_async_runner_when_enabled(tmp_path: Path):
    config = SyncConfig(
        db_path=tmp_path / "compras.duckdb",
        ops_db_path=tmp_path / "compras_ops.sqlite",
        base_url="https://dadosabertos.compras.gov.br",
        async_mode=True,
        concurrency=3,
    )

    runner = build_runner(config)

    assert isinstance(runner, AsyncSyncRunner)


def test_async_sync_runner_fetches_known_pages_and_serializes_bronze_pages(tmp_path: Path):
    base_db_path = tmp_path / "compras.duckdb"
    ops_db_path = tmp_path / "compras_ops.sqlite"
    job = EndpointJob(
        name="uasg_status_true",
        operation_id="consultarUasg",
        path="/modulo-uasg/1_consultarUasg",
        entity_name="uasg",
        key_fields=("codigoUasg", "codigo_uasg"),
        base_params={"statusUasg": True},
    )
    pages = {
        1: PageData(
            url="https://dadosabertos.compras.gov.br/modulo-uasg/1_consultarUasg",
            page_number=1,
            params={"pagina": 1, "statusUasg": True},
            records=[{"codigoUasg": "1", "nomeUasg": "A"}],
            raw={"resultado": [{"codigoUasg": "1", "nomeUasg": "A"}], "totalPaginas": 3, "paginasRestantes": 2},
            content_type="application/json",
            status_code=200,
        ),
        2: PageData(
            url="https://dadosabertos.compras.gov.br/modulo-uasg/1_consultarUasg",
            page_number=2,
            params={"pagina": 2, "statusUasg": True},
            records=[{"codigoUasg": "2", "nomeUasg": "B"}],
            raw={"resultado": [{"codigoUasg": "2", "nomeUasg": "B"}], "totalPaginas": 3, "paginasRestantes": 1},
            content_type="application/json",
            status_code=200,
        ),
        3: PageData(
            url="https://dadosabertos.compras.gov.br/modulo-uasg/1_consultarUasg",
            page_number=3,
            params={"pagina": 3, "statusUasg": True},
            records=[{"codigoUasg": "3", "nomeUasg": "C"}],
            raw={"resultado": [{"codigoUasg": "3", "nomeUasg": "C"}], "totalPaginas": 3, "paginasRestantes": 0},
            content_type="application/json",
            status_code=200,
        ),
    }
    client = FakeAsyncClient(pages)
    runner = AsyncSyncRunner(
        config=SyncConfig(
            db_path=base_db_path,
            ops_db_path=ops_db_path,
            base_url="https://dadosabertos.compras.gov.br",
            resume=True,
            async_mode=True,
            concurrency=2,
        ),
        client=client,
        jobs=(job,),
    )

    run_id = runner.run()

    assert run_id
    assert client.calls == [1, 2, 3]
    with runner.warehouse.connect() as con:
        assert con.execute("select count(*) from bronze_pages").fetchone()[0] == 3
        tables = {row[0] for row in con.execute("select table_name from duckdb_tables()").fetchall()}
        assert tables == {"bronze_pages"}
    with runner.ops_store.connect() as con:
        assert con.execute("select status from ops_runs where run_id = ?", [run_id]).fetchone()[0] == "finished"
        assert con.execute("select next_page from ops_checkpoints where job_name = ?", [job.name]).fetchone()[0] == 4
