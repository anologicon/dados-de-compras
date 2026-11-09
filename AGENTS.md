# AGENTS.md — routing table

This file is a router only. It contains no substantive rules or context; it points to the documents that do.

**Read `agent_state.json` at the start of every turn. Update it before ending the turn.**
It is the system of record for agent work: active task id, touched files, assumptions, blockers, next action. It is local-only (gitignored, never committed). A new session reads it instead of replaying chat.

**`task_board.json` is the queue.** When `agent_state.json` is empty (no active task), pull the next `todo` task from it. It is small on purpose: if it grows past a screen, fix the planning, not the board. Tasks carry `id`, `goal`, `owner` (`builder` | `reviewer` | `human`), `status` (`todo` | `in_progress` | `done` | `blocked`), and `acceptance_criteria`. Do not mark a task `done` while any criterion is unmet.

## Routing map

| If you are going to… | Read |
|---|---|
| Orient yourself in the repo, architecture, commands, conventions | `README.md` |
| Find the next task after your current one is done, or check whether work is on track | `task_board.json` |
| Work on any Compras.gov.br source/endpoint | `docs/API_COMPRAS_GOV.md` |
| Work on the PNCP direct source (client, collector, orchestrator) | `docs/API_PNCP_DIRECT.md` and `docs/PNCP_DIRECT_PLAN.md` |
| Work on the optional web app or frontend | `docs/WEB_PLAN.md` |
| Plan or scope work inside the controlled evolution cycle | `docs/evolution/README.md` |
| Make or revise an architectural decision | `docs/evolution/decisions.md` |
| Touch Bronze schemas or storage contracts | `docs/evolution/unified-storage-contract.md` |
| Change or triage the backlog | `docs/evolution/backlog.md` |
| Run a supervised evolution workflow (evoluir / status / executar / aceitar) | `.pi/prompts/evoluir.md` and the sibling prompts in `.pi/prompts/` |
| Behave as one of the evolution agents (product/implementer/reviewer/qa/investigator) | Your role definition in `.pi/agents/` |
| Update or operate the read-only MCP server / bounded project access | `docs/MCP.md`, `src/compras_crawler/project_access.py` |
| Work on the entity explorer | `docs/ENTITY_EXPLORER.md` |
| Consult past research or scouting notes | `context/` |

## Hard rules (each enforced by its document)

1. Raw Bronze is the source of truth and is never replaced or rewritten by normalized data — `README.md`, *Important conventions*.
2. `COMPRAS_GOV_TOKEN` is for Compras.gov.br only and is never sent to PNCP — `docs/API_PNCP_DIRECT.md`.
3. Network-dependent code must be testable fully offline before any real request, and the test suite (`tests/`) must pass green before any commit.
4. The real Brusque pilot (and any live collection of new data) requires explicit separate authorization — `docs/PNCP_DIRECT_PLAN.md`.
5. `ops/` SQLite stores and `*.duckdb` files are runtime artifacts; do not commit, copy, or delete them as part of code changes.
