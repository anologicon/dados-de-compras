from __future__ import annotations

from pathlib import Path
from typing import Any

from ..storage import migrate_bronze_database
from .analytics import build_snapshot
from .runtime import file_lock
from .store import AppStore


def import_seed(store: AppStore, source: Path, city_id: str, name: str, uf: str) -> dict[str, Any]:
    """Explicit CLI-only import. No HTTP endpoint accepts filesystem paths."""
    source = source.resolve(strict=True)
    store.init_schema()
    target = store.city_dir(city_id) / "bronze.duckdb"
    with file_lock(store.root / "service.lock"), file_lock(store.city_dir(city_id) / "writer.lock"):
        if target.exists():
            raise FileExistsError("já existe Bronze gerenciado para este município; importação não sobrescreve dados")
        store.add_city(city_id, name, uf)
        result = migrate_bronze_database(source_db_path=source, bronze_db_path=target)
        if result.bronze_pages == 0:
            target.unlink(missing_ok=True)
            raise ValueError("origem não contém páginas Bronze; nenhuma análise foi publicada")
        summary = build_snapshot(store, city_id)
    return dict(city_id=city_id, bronze_pages=result.bronze_pages, coverage=summary)
