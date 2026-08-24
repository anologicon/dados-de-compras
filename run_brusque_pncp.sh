#!/usr/bin/env bash
set -euo pipefail

compras-crawler sync \
  --start-date 2026-01-01 \
  --end-date 2026-12-31 \
  --state-uf SC \
  --municipality-code 4202909 \
  --source pncp \
  --pncp-modalidade-code 3 \
  --pncp-modalidade-code 5 \
  --pncp-modalidade-code 8 \
  --pncp-modalidade-code 10 \
  --db-path dados_abertos_compras \
  --no-ui
