# Project Context

## What this repo is
`compras-crawler` crawls public procurement data from **Compras.gov.br** into **Bronze** DuckDB files. An optional local web application adds collection management and rebuildable read-only analytical projections.

## Main goals
- Fetch public API data from `https://dadosabertos.compras.gov.br`
- Support JSON and CSV API responses
- Persist raw fetched pages in a Bronze DuckDB
- Keep raw Bronze as the source of truth; web projections are disposable, separate files
- Resume syncs with checkpoints
- Offer optional local exploration, a persistent collection queue, and schedules

## Current architecture
- `src/compras_crawler/client.py` — HTTP client, pagination, JSON/CSV parsing
- `src/compras_crawler/manifest.py` — job manifest for historical syncs
- `src/compras_crawler/normalize.py` — response record extraction and stable hashing helpers
- `src/compras_crawler/storage.py` — Bronze DuckDB schema, persistence, and legacy Bronze migration
- `src/compras_crawler/sync.py` — orchestration runner
- `src/compras_crawler/cli.py` — CLI entrypoint
- `src/compras_crawler/crawl_state.py` — atomic full-city page/checkpoint persistence
- `src/compras_crawler/web/` — optional API, persistent queue/scheduler, isolated workers, analytical projections
- `frontend/` — React/TypeScript interface and browser tests
- `src/compras_crawler/mcp_server.py` — read-only MCP server (`compras-crawler mcp` or `compras-mcp`)
- `src/compras_crawler/project_access.py` — bounded documentation and database queries
- `docs/API_COMPRAS_GOV.md` — API reference and conventions
- `context/` — project notes and research

## Important conventions
- Pagination uses `pagina` and often 1-based numbering
- Dates are usually `YYYY-MM-DD`
- CSV endpoints may be selected via `Accept: text/csv`
- Auth uses bearer token only for jobs/endpoints marked as requiring it (`COMPRAS_GOV_TOKEN`, optionally loaded from `.env`)
- `--base-url` must use HTTPS; tokened runs are restricted to `https://dadosabertos.compras.gov.br`
- The crawler never replaces raw Bronze with normalized data. Web projections live in their own managed workspace.

## Local web UI (initial implementation)

Install the optional backend and compile the frontend (Node is needed only for build/development):
```bash
.venv/bin/pip install -e '.[web,web-test]'
npm --prefix frontend ci
npm --prefix frontend run build
```

Before starting the service, optionally import the existing Florianópolis Bronze. This copies raw pages into a managed municipal database and never overwrites the original:
```bash
.venv/bin/compras-crawler web-import \
  --source-db-path dados_abertos_compras_florianopolis_api_inteira_bronze.duckdb \
  --municipality-code 4205407 --city-name Florianópolis --state-uf SC
```

Start manually:
```bash
.venv/bin/compras-crawler web
```
Open **http://127.0.0.1:8000**. Use `--workspace /path/to/private/workspace` or `--port 8001` if needed. The service binds only to loopback; do not expose it through a public proxy. Imports require the service to be stopped and refuse to overwrite an existing municipal Bronze.

Available now:
- Official IBGE municipality search by UF and name/code, with automatic read-only code fill and server-side identity validation
- Publication-cohort panorama, municipality selection, date/object/organization/modality filters
- Deduplicated purchases, original JSON/provenance, generic entity inspection
- Streaming CSV/JSON export of the entire filtered population; CSV formula protection
- Persistent full-city queue, two isolated city workers, global request pacing/cooldown
- Cooperative stop/resume, recovery, daily/weekly/one-off schedules with explicit timezone
- Immutable analytical snapshots published at the end; the previous version stays readable

Municipality registration downloads the official IBGE catalog through the backend, caches it in `app.sqlite` for 30 days, and offers **Atualizar catálogo** for explicit refresh. Search ignores case/accents and filters by UF. If IBGE is unavailable, the last valid catalog remains usable with a warning when an update fails; without a saved catalog, new unverified registrations are blocked. Existing municipalities and their collections remain usable.

Schedules run only while this process is alive. Closing the browser does not stop them; stopping the service does. On restart, interrupted work resumes and missed schedule slots are coalesced. Recurrent jobs default to a rolling 90-day window; older history is **not** refreshed automatically. A new collection re-queries the API; resuming an existing collection reuses only its confirmed pages.

The workspace (default `.compras-web/`, ignored by Git) contains `app.sqlite` and `cities/<IBGE>/{bronze.duckdb,ops.sqlite,snapshots/}`. Bronze is retained; projections keep the current and previous versions. New requests stop when free space reaches the configured reserve (`--reserve-gib`, default 5). Tokens are read from the server environment/`.env`, never accepted by the web API.

Imported data is labeled **coverage unverified**. Explicit identity conflicts, unknown publication dates, and unproven municipal membership are excluded from consolidated metrics. Missing monetary values remain unknown, not zero. Estimado, homologado, and contratado are distinct from paid expenditure. The generic explorer shows the latest observed record per identity (ordered by fetch time, with API update time only as a tie-breaker); all original page versions remain in Bronze.

**Not final acceptance:** dedicated supplier/contract/price analyses and full live-module validation are still pending. The strict Brusque acceptance crawl has not yet been executed. See [docs/WEB_PLAN.md](docs/WEB_PLAN.md).

Tests:
```bash
.venv/bin/pytest -q
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```
Browser tests use a temporary synthetic dataset, with workers disabled and no calls to the public API. Install Chromium once with `cd frontend && npx playwright install chromium`.

## CLI usage
```bash
compras-crawler sync --db-path dados_abertos_compras
```
`--db-path` is a base/prefix. The example above creates `dados_abertos_compras_bronze.duckdb` and `ops/dados_abertos_compras_ops.sqlite`. Passing `--db-path compras.duckdb` derives `compras_bronze.duckdb` and `ops/compras_ops.sqlite` for compatibility.

Default output is an enriched terminal UI: full-screen TUI when running on a TTY, and friendly console progress when output is captured or redirected.

Guided interactive menu/TUI:
```bash
compras-crawler menu
```
The menu is a step-by-step wizard with contextual help (`?`), validated inputs, operation selection by number/id/range, and a final command review. Use `compras-crawler menu --dry-run` to build and print the equivalent `sync` command without executing it.

Best-effort full public API crawl for one municipality (derives IDs and fans out to PNCP, UASG/órgão, legado, ARP, contratos, PGC, OCDS, fornecedores, catálogo, and pesquisa de preço endpoints):
```bash
compras-crawler full-city \
  --start-date 2026-01-01 \
  --end-date 2026-12-31 \
  --state-uf SC \
  --municipality-code 4205407 \
  --db-path dados_abertos_compras_florianopolis_api_inteira
```
If `COMPRAS_GOV_TOKEN` is configured, `full-city` first calls endpoints without auth and only retries with Bearer auth after `401/403`. Protected/admin endpoints such as `USUARIOS` and `ALICE` are skipped by default.

Swagger-style example:
```bash
compras-crawler sync --operation consultarUasg --start-date 2024-01-01 --end-date 2024-01-31
```
Municipality-specific purchases:
```bash
compras-crawler sync --municipality-code 4202909 --state-uf SC --source pncp --pncp-modalidade-code 8
```

Concurrent page fetching with serial DuckDB writes (requests are still globally paced by `--delay-seconds` to avoid API rate limits):
```bash
compras-crawler sync --operation consultarUasg --async --concurrency 5 --delay-seconds 1.0
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
- `--delay-seconds 1.0` minimum delay between HTTP requests to avoid 429 rate limits
- `--rate-limit-sleep-seconds 60` cooldown used before retrying after HTTP 429
- `--request-timeout 45` and `--request-retries 5` for HTTP robustness
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
- `bronze_crawl_jobs` — full-city generation/completion state; committed atomically with each page

Ops SQLite:
- `ops_runs` — sync runs and Bronze DB path
- `ops_checkpoints` — resume state
- `ops_errors` — failures

Legacy migration:
```bash
compras-crawler migrate-bronze --source-db-path compras.duckdb --db-path dados_abertos_compras
```
Use `--overwrite` if the target Bronze file already exists and should be replaced.

## MCP para agentes

Instale o suporte opcional e inicie o servidor local via `stdio`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[mcp]"
.venv/bin/compras-crawler mcp --project-root . \
  --db-path dados_abertos_compras_bronze.duckdb \
  --ops-db-path ops/dados_abertos_compras_ops.sqlite
# A mesma configuração pode ser usada com o executável compras-mcp.
```

O MCP lê a Bronze atual sem criar tabelas derivadas e mantém compatibilidade
com bases legadas que já contenham `silver_records`.
O processo aguarda um cliente MCP; não é uma interface interativa. Veja
[docs/MCP.md](docs/MCP.md) para configurar agentes, consultar as ferramentas e executar testes.

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
