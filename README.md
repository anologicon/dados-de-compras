# Project Context

## What this repo is
`compras-crawler` is a Python project for crawling public procurement data from **Compras.gov.br** into a **Bronze** DuckDB file.

## Main goals
- Fetch public API data from `https://dadosabertos.compras.gov.br`
- Support JSON and CSV API responses
- Persist raw fetched pages in a Bronze DuckDB
- Leave Silver and Gold processing to downstream projects/jobs
- Resume syncs with checkpoints

## Current architecture
- `src/compras_crawler/client.py` — HTTP client, pagination, JSON/CSV parsing
- `src/compras_crawler/manifest.py` — job manifest for historical syncs
- `src/compras_crawler/normalize.py` — response record extraction and stable hashing helpers
- `src/compras_crawler/storage.py` — Bronze DuckDB schema, persistence, and legacy Bronze migration
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
- The crawler stores raw Bronze pages only; Silver/Gold deduping and marts are out of scope here

## CLI usage
```bash
compras-crawler sync --db-path dados_abertos_compras
```
`--db-path` is a base/prefix. The example above creates `dados_abertos_compras_bronze.duckdb` and `dados_abertos_compras_ops.sqlite`. Passing `--db-path compras.duckdb` derives `compras_bronze.duckdb` for compatibility.

Default output is an enriched terminal UI: full-screen TUI when running on a TTY, and friendly console progress when output is captured or redirected.

Guided interactive menu/TUI:
```bash
compras-crawler menu
```
The menu is a step-by-step wizard with contextual help (`?`), validated inputs, operation selection by number/id/range, and a final command review. Use `compras-crawler menu --dry-run` to build and print the equivalent `sync` command without executing it.

Swagger-style example:
```bash
compras-crawler sync --operation consultarUasg --start-date 2024-01-01 --end-date 2024-01-31
```
Municipality-specific purchases:
```bash
compras-crawler sync --municipality-code 4202909 --state-uf SC --source pncp --pncp-modalidade-code 8
```

Concurrent page fetching with serial DuckDB writes:
```bash
compras-crawler sync --operation consultarUasg --async --concurrency 5
```

Useful flags:
- `--db-path` base/prefix for the Bronze DB (default: `dados_abertos_compras`)
- `--bronze-db-path` for an explicit Bronze file
- `--ops-db-path` for operation metadata/checkpoints SQLite
- `--base-url` (HTTPS only)
- `--start-date`
- `--end-date`
- `--page-size`
- `--async` to fetch pages concurrently while preserving serial writes
- `--concurrency 5` to control the async page-fetch fanout
- `--operation consultarUasg|consultarLicitacao|consultarContratacoes_PNCP_14133|...` (repeatable)
- `--state-uf SP` to restrict supported jobs by UF
- `--municipality-code 3550308` + `--source pncp` + repeatable `--pncp-modalidade-code` values for city-specific purchase runs
- `--list-operations` to preview what will run
- `--no-resume`
- `--log-level DEBUG|INFO|WARNING|ERROR|CRITICAL`
- `--ui auto|tui|console|none` to choose the progress UI
- `--tui` to force the full-screen terminal UI
- `--no-ui` to disable progress UI output

## Data model
Bronze DuckDB:
- `bronze_pages` — raw fetched pages

Ops SQLite:
- `ops_runs` — sync runs and Bronze DB path
- `ops_checkpoints` — resume state
- `ops_errors` — failures

Legacy migration:
```bash
compras-crawler migrate-bronze --source-db-path compras.duckdb --db-path dados_abertos_compras
```
Use `--overwrite` if the target Bronze file already exists and should be replaced.

## When editing
- Prefer small, targeted changes
- Keep sync/idempotency behavior intact
- Update tests if behavior changes
- If API behavior is unclear, check `docs/API_COMPRAS_GOV.md` first

## Good starting points for new work
- Add or adjust endpoint jobs in `manifest.py`
- Improve response extraction/hash helpers in `normalize.py`
- Extend Bronze storage schema in `storage.py`
- Add CLI flags in `cli.py`
