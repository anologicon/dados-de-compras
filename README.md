# Project Context

## What this repo is
`compras-crawler` is a Python project for crawling and syncing public procurement data from **Compras.gov.br** into **DuckDB**.

## Main goals
- Fetch public API data from `https://dadosabertos.compras.gov.br`
- Support JSON and CSV API responses
- Persist raw pages and normalized records in DuckDB
- Resume syncs with checkpoints

## Current architecture
- `src/compras_crawler/client.py` — HTTP client, pagination, JSON/CSV parsing
- `src/compras_crawler/manifest.py` — job manifest for historical syncs
- `src/compras_crawler/normalize.py` — record normalization and stable hashing
- `src/compras_crawler/storage.py` — DuckDB schema and persistence
- `src/compras_crawler/sync.py` — orchestration runner
- `src/compras_crawler/cli.py` — CLI entrypoint (`compras-crawler sync`)
- `docs/API_COMPRAS_GOV.md` — API reference and conventions
- `context/` — project notes and research

## Important conventions
- Pagination uses `pagina` and often 1-based numbering
- Dates are usually `YYYY-MM-DD`
- CSV endpoints may be selected via `Accept: text/csv`
- Auth uses bearer token when needed (`COMPRAS_GOV_TOKEN`, optionally loaded from `.env`)
- `--base-url` must use HTTPS; tokened runs are restricted to `https://dadosabertos.compras.gov.br`
- Records are deduped using entity-specific key fields; fallback is a stable hash

## CLI usage
```bash
compras-crawler sync --db-path compras.duckdb
```
Default output is a friendly live console UI with progress, ETA, spinner, and colors.

Swagger-style example:
```bash
compras-crawler sync --operation consultarUasg --start-date 2024-01-01 --end-date 2024-01-31
```

Useful flags:
- `--base-url` (HTTPS only)
- `--start-date`
- `--end-date`
- `--page-size`
- `--operation consultarUasg|consultarLicitacao|consultarContratacoes_PNCP_14133|...` (repeatable)
- `--state-uf SP` to restrict supported jobs by UF
- `--municipality-code 3550308` + `--pncp-modalidade-code 8` for a city-specific PNCP run
- `--list-operations` to preview what will run
- `--no-resume`
- `--log-level DEBUG|INFO|WARNING|ERROR|CRITICAL`
- `--no-ui` to disable the friendly console output

## Data model
DuckDB tables:
- `bronze_pages` — raw fetched pages
- `silver_records` — normalized upserts
- `ops_runs` — sync runs
- `ops_checkpoints` — resume state
- `ops_errors` — failures

## When editing
- Prefer small, targeted changes
- Keep sync/idempotency behavior intact
- Update tests if behavior changes
- If API behavior is unclear, check `docs/API_COMPRAS_GOV.md` first

## Good starting points for new work
- Add or adjust endpoint jobs in `manifest.py`
- Improve normalization rules in `normalize.py`
- Extend storage schema in `storage.py`
- Add CLI flags in `cli.py`
