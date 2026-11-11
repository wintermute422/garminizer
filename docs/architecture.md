# Architecture

```
Garmin Connect ──(garminconnect, read-only, throttled)──▶ worker / app
                                                            │
                         raw_payload (verbatim JSON) ◀──────┤  fetch
                                   │                        │
                                   ▼ parse (idempotent)     │
        typed tables: activities, samples (FIT), sleep, HRV, stress, …
                                   │
                                   ▼ analytics pipeline
        best efforts, zones, splits, tracks, tiles, daily load (CTL/ATL/TSB) + SQL views
                                   │
                                   ▼
                FastAPI  /api/*  (SI units, OpenAPI)  ──▶  React SPA (ECharts, MapLibre)

Claude Desktop ──(MCP over stdio: docker exec … garminizer mcp)──▶ meal, meal_item
                 (Claude estimates foods and nutrients; Garminizer validates and stores)
```

## Services (`compose.yml`)
| Service | What it does |
|---|---|
| `db` | PostgreSQL 17, schema `garmin`, named volume `pgdata` |
| `app` | `garminizer serve`: runs migrations, serves `/api` and the built dashboards on port 8420 |
| `worker` | `garminizer worker`: incremental sync every `SYNC_INTERVAL_HOURS` (and on start), budgeted backfill until the whole history is in, nightly `pg_dump` backup at 03:30 |

## Backend (`backend/garminizer/`)
| Package | Responsibility |
|---|---|
| `config.py` | settings from environment / `.env`; refuses unsafe exposure without a password |
| `athlete.py` | the athlete's clock: the one rule for "today" and local days (Garmin's profile time zone, else `TZ`, else UTC), used by the API, MCP, sync and analytics |
| `db/` | SQLAlchemy base, sessions, bulk COPY/upsert helpers, Alembic migrations (shipped in the package) |
| `models/` | every table, each with a comment ([data model](data-model.md)) |
| `garmin/` | read-only client wrapper (whitelist, throttle, backoff) and login/MFA/token handling |
| `sync/` | dataset registry, parsers, FIT decoding, `plan` (pure: which days/months in which order), engine (executes the plan: incremental, backfill, reparse, run bookkeeping), `service` (the one entry point for worker, API and CLI: preconditions, token resume, an `Outcome` each caller maps), verify |
| `analytics/` | pure numpy functions (TRIMP, mean-max, PMC, LTTB, tiles, …) and the pipeline that writes derived tables |
| `api/` | FastAPI app, auth, one thin router per dashboard; `activity_sql.py` holds the shared activity filter (range + sport), summary columns and moving time |
| `insights.py` | insights read model: daily metric grid, correlations, scatter and plain-English cards (pure, unit-tested without a database) |
| `demo/` | the synthetic athlete simulator behind `garminizer demo seed` (including a meal diary) |
| `nutrition/` | meal log: validation, totals and plausibility warnings, day/period summaries against Garmin's energy burn, targets |
| `mcp_server.py` | `garminizer mcp`: Model Context Protocol server over stdio for Claude Desktop (log/correct meals, day summaries, energy context); see [claude-desktop.md](claude-desktop.md) |
| `worker.py`, `backup.py` | scheduler and pg_dump/pg_restore |

### Why raw-first?
Every Garmin response is stored verbatim before it is parsed. When a parser improves, `garminizer
reparse` rebuilds all typed tables without downloading anything again — kinder to Garmin's servers
and to your rate limit.

### Sync strategy
Daily datasets are fetched per day (or per range where Garmin offers one), activities page by page
with their details and the original FIT file (full-resolution samples). Each unit of work commits on
its own and advances a per-dataset cursor, so a crash or a closed laptop simply resumes. A Postgres
advisory lock guarantees one sync at a time across app and worker.

## Frontend (`web/`)
React 19, Vite, TanStack Router + Query, a typed client generated from the OpenAPI schema,
Tailwind CSS v4 tokens, Apache ECharts 6 for charts and MapLibre GL for maps. Global filters
(date range, sport) live in the URL so every view is shareable. See
[`web/CONVENTIONS.md`](../web/CONVENTIONS.md).

## Quality gates
`scripts/check.sh` (lint, strict types, unit/integration tests, build, API-type freshness, secret
scan) and `scripts/e2e.sh` (every page × 4 variants with chart/map/console/overflow/axe checks) run
locally and in CI. See [development.md](development.md).
