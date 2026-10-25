import pytest
import requests

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from compras_crawler.web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = create_app(tmp_path, start_workers=False, reserve_bytes=0)
    monkeypatch.setattr(app.state.catalog, "_download", lambda: [
        {"id": 4202909, "nome": "Brusque"}, {"id": 4205407, "nome": "Florianópolis"},
        {"id": 4216602, "nome": "São José"}, {"id": 3549904, "nome": "São José dos Campos"},
    ])
    with TestClient(app, base_url="http://127.0.0.1:8000", headers={"X-Compras-UI": "1"}) as client:
        yield client


def add_city(client):
    assert client.post("/api/cities", json=dict(id="4202909", name="Brusque", uf="SC")).status_code == 201


def test_local_security_and_csrf_boundary(client):
    assert client.get("/api/status", headers={"Host": "attacker.example:8000"}).status_code == 400
    assert client.post("/api/cities", json={}, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.post("/api/cities", json={}, headers={"X-Compras-UI": ""}).status_code == 403
    assert client.get("/api/status").headers["x-content-type-options"] == "nosniff"
    assert client.post("/api/municipalities/refresh", headers={"X-Compras-UI": ""}).status_code == 403


def test_create_city_and_validate_inputs(client):
    add_city(client)
    assert client.get("/api/cities").json()[0]["id"] == "4202909"
    assert client.post("/api/cities", json=dict(id="../etc/", name="Invalid", uf="SC")).status_code == 422
    assert client.post("/api/cities", json=dict(id="4202909", name="Invalid", uf="XX")).status_code == 422
    assert client.post("/api/cities", json=dict(id="4202909", name="Invalid", uf="SP")).status_code == 422
    assert client.post("/api/runs", json=dict(city_id="4202909", start_date="2026-02-01", end_date="2026-01-01")).status_code == 422
    assert client.post("/api/runs", json=dict(city_id="4202909", start_date="2026-01-01", end_date="2026-01-31", token="secret")).status_code == 422


def test_search_official_catalog_and_reject_manual_identity(client):
    response = client.get("/api/municipalities", params={"uf": "sc", "q": "florianopolis"})
    assert response.status_code == 200
    assert response.json()["items"] == [{"id": "4205407", "name": "Florianópolis", "uf": "SC"}]
    assert client.get("/api/municipalities?uf=SC&q=sao").json()["total"] == 1
    assert client.get("/api/municipalities?uf=ZZ&q=brusque").status_code == 400
    assert client.get("/api/municipalities?uf=SC&q=b").status_code == 422
    assert client.get("/api/municipalities?uf=SC&q=%20%20").status_code == 400
    assert client.get("/api/municipalities?uf=SC&q=br&limit=1000").status_code == 422
    assert client.post("/api/cities", json=dict(id="4202909", name="Nome inventado", uf="SC")).status_code == 400
    assert client.post("/api/cities", json=dict(id="4200000", name="Não existe", uf="SC")).status_code == 400
    assert client.get("/api/cities").json() == []
    assert client.post("/api/municipalities/refresh").status_code == 200


def test_ibge_outage_does_not_block_existing_cities_or_allow_manual_registration(client, monkeypatch):
    def unavailable():
        raise requests.Timeout()
    client.app.state.store.add_city("4202909", "Brusque", "SC")
    monkeypatch.setattr(client.app.state.catalog, "_download", unavailable)
    result = client.get("/api/municipalities?uf=SC&q=florianopolis")
    assert result.status_code == 503 and "sem catálogo oficial" in result.json()["detail"]
    assert client.post("/api/cities", json=dict(id="4205407", name="Florianópolis", uf="SC")).status_code == 503
    assert len(client.get("/api/cities").json()) == 1
    assert client.post("/api/runs", json=dict(city_id="4202909", start_date="2026-01-01", end_date="2026-01-31")).status_code == 201


def test_enqueue_stop_and_resume(client):
    add_city(client)
    created = client.post("/api/runs", json=dict(city_id="4202909", start_date="2026-01-01", end_date="2026-01-31"))
    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "queued"
    assert client.post(f"/api/runs/{run['id']}/stop").json()["status"] == "stopped"
    assert client.post(f"/api/runs/{run['id']}/resume").json()["status"] == "queued"
    assert client.get("/api/runs").json()[0]["config"]["start_date"] == "2026-01-01"


def test_schedule_validation_and_pause(client):
    add_city(client)
    values = dict(city_id="4202909", name="Diária", frequency="daily", timezone="America/Sao_Paulo", local_time="02:00")
    result = client.post("/api/schedules", json=values)
    assert result.status_code == 201
    assert client.patch(f"/api/schedules/{result.json()['id']}", json={"enabled": False}).status_code == 200
    assert not client.get("/api/schedules").json()[0]["enabled"]
    assert client.post("/api/schedules", json=dict(values, timezone="Bad/Zone")).status_code == 422
    assert client.post("/api/schedules", json=dict(values, frequency="weekly")).status_code == 422
    assert client.post("/api/schedules", json=dict(values, frequency="once", due_at="2099-01-01T02:00:00Z")).status_code == 201


def test_missing_city_and_missing_snapshot_are_explicit(client):
    assert client.get("/api/cities/0000000/overview").status_code == 404
    add_city(client)
    response = client.get("/api/cities/4202909/overview")
    assert response.status_code == 400
    assert "primeira coleta" in response.json()["detail"]
