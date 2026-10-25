from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal
import json
import shutil

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import analytics
from .models import CityInput, EnabledInput, RunInput, ScheduleInput
from .municipalities import CatalogUnavailable, MunicipalityCatalog
from .runtime import Service
from .store import AppStore

STATIC = Path(__file__).parent / "static"


def create_app(workspace: str | Path = ".compras-web", *, port: int = 8000,
               start_workers: bool = True, reserve_bytes: int = 5 * 1024**3) -> FastAPI:
    store = AppStore(workspace)
    service = Service(store, reserve_bytes=reserve_bytes)
    catalog = MunicipalityCatalog(store)
    origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    @asynccontextmanager
    async def lifespan(app):
        store.init_schema()
        catalog.init_schema()
        if start_workers:
            service.start()
        try:
            yield
        finally:
            if start_workers:
                service.close()

    app = FastAPI(title="Compras · Observatório local", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store, app.state.service, app.state.catalog = store, service, catalog

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        origin = f"http://{request.headers.get('host', '')}"
        if origin not in origins:
            return JSONResponse({"detail": "Host não permitido; use localhost."}, status_code=400)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if (request.headers.get("x-compras-ui") != "1"
                or request.headers.get("origin", origin) not in origins
                or request.headers.get("sec-fetch-site") == "cross-site"):
                return JSONResponse({"detail": "Requisição de outra origem não permitida."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'; object-src 'none'"
        )
        if request.url.path.startswith("/api/") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": str(exc).strip("'")}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(CatalogUnavailable)
    async def catalog_unavailable(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.get("/api/municipalities")
    def municipalities(uf: str = Query(min_length=2, max_length=2),
                       q: str = Query(min_length=2, max_length=100),
                       limit: int = Query(default=20, ge=1, le=50)):
        return catalog.search(uf, q, limit)

    @app.post("/api/municipalities/refresh")
    def refresh_municipalities():
        return catalog.ensure(refresh=True)

    @app.get("/api/status")
    def status():
        return dict(service="running" if start_workers else "disabled", max_workers=2,
                    request_interval_seconds=1, free_disk_bytes=shutil.disk_usage(store.root).free,
                    reserve_bytes=reserve_bytes, error=service.error)

    @app.get("/api/cities")
    def cities():
        data = store.cities()
        for city in data:
            city["coverage"] = json.loads(city.pop("coverage_json") or "null")
            city["has_snapshot"] = bool(city.pop("snapshot"))
            city.pop("previous_snapshot", None)
        return data

    @app.post("/api/cities", status_code=201)
    def add_city(body: CityInput):
        official = catalog.municipality(body.id)
        if body.name != official["name"] or body.uf != official["uf"]:
            raise ValueError("Nome ou UF divergem do catálogo oficial. Selecione novamente o município na busca.")
        return store.add_city(official["id"], official["name"], official["uf"])

    @app.get("/api/runs")
    def runs():
        return store.runs()

    @app.post("/api/runs", status_code=201)
    def enqueue(body: RunInput):
        values = body.model_dump(mode="json")
        city_id = values.pop("city_id")
        return store.run(store.enqueue(city_id, values))

    @app.post("/api/runs/{run_id}/stop")
    def stop(run_id: str):
        store.request_stop(run_id)
        return store.run(run_id)

    @app.post("/api/runs/{run_id}/resume")
    def resume(run_id: str):
        store.resume(run_id)
        return store.run(run_id)

    @app.get("/api/runs/{run_id}/events")
    def events(run_id: str, after: int = Query(default=0, ge=0)):
        store.run(run_id)
        return store.events(run_id, after)

    @app.get("/api/schedules")
    def schedules():
        return store.schedules()

    @app.post("/api/schedules", status_code=201)
    def add_schedule(body: ScheduleInput):
        values = body.model_dump(mode="json")
        schedule_id = store.add_schedule(values)
        return next(s for s in store.schedules() if s["id"] == schedule_id)

    @app.patch("/api/schedules/{schedule_id}")
    def enable_schedule(schedule_id: str, body: EnabledInput):
        store.enable_schedule(schedule_id, body.enabled)
        return {"enabled": body.enabled}

    def filters(start_date, end_date, q, modality, org_name):
        if start_date and end_date and start_date > end_date:
            raise ValueError("período inválido")
        return dict(start_date=start_date.isoformat() if start_date else None,
                    end_date=end_date.isoformat() if end_date else None, q=q, modality=modality, org_name=org_name)

    @app.get("/api/cities/{city_id}/overview")
    def overview(city_id: str, start_date: date | None = None, end_date: date | None = None,
                 q: str = Query(default="", max_length=300), modality: str = Query(default="", max_length=100),
                 org_name: str = Query(default="", max_length=300)):
        return analytics.overview(store, city_id, filters(start_date, end_date, q, modality, org_name))

    @app.get("/api/cities/{city_id}/purchases")
    def purchases(city_id: str, start_date: date | None = None, end_date: date | None = None,
                  q: str = Query(default="", max_length=300), modality: str = Query(default="", max_length=100),
                  org_name: str = Query(default="", max_length=300), page: int = Query(default=1, ge=1),
                  page_size: int = Query(default=25, ge=1, le=100)):
        return analytics.purchases(store, city_id, filters(start_date, end_date, q, modality, org_name), page, page_size)

    @app.get("/api/cities/{city_id}/entities")
    def entities(city_id: str):
        return analytics.entities(store, city_id)

    @app.get("/api/cities/{city_id}/records")
    def records(city_id: str, entity: str = Query(max_length=100), q: str = Query(default="", max_length=300),
                page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100)):
        return analytics.raw_records(store, city_id, entity, q, page, page_size)

    @app.get("/api/cities/{city_id}/export")
    def export(city_id: str, format: Literal["csv", "json"] = "csv", start_date: date | None = None,
               end_date: date | None = None, q: str = Query(default="", max_length=300),
               modality: str = Query(default="", max_length=100), org_name: str = Query(default="", max_length=300)):
        analytics.snapshot_path(store, city_id)
        selected = filters(start_date, end_date, q, modality, org_name)
        return StreamingResponse(analytics.export_purchases(store, city_id, selected, format),
            media_type="text/csv; charset=utf-8" if format == "csv" else "application/json",
            headers={"Content-Disposition": f'attachment; filename="compras_{city_id}.{format}"'})

    if (STATIC / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/")
    def index():
        if not (STATIC / "index.html").exists():
            raise HTTPException(503, "Frontend não compilado. Execute: cd frontend && npm ci && npm run build")
        return FileResponse(STATIC / "index.html")

    return app
