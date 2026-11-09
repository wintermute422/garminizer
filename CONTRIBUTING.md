# Contributing

Thanks for helping! Garminizer handles personal health data, so a few rules are stricter than usual.

## Ground rules
- **No real personal data anywhere in the repository** — not in code, fixtures, logs, issues,
  screenshots or commit messages. Use the demo generator (`garminizer demo seed`) for screenshots
  and reproductions; fixtures are synthetic. The git hooks and CI scan for secrets and personal data.
- **Garmin accounts are read-only.** The client only reaches an explicit whitelist of read
  methods (`backend/garminizer/garmin/client.py`); a test enforces it.
- Do not weaken a test or a threshold to make a change pass — fix the code.
- **Commit with your GitHub noreply address** (GitHub → Settings → Emails → *Keep my email
  addresses private* shows it): `git config user.email <id>+<login>@users.noreply.github.com`.
  The hooks and CI reject commits whose author or committer e-mail is not a noreply address.

## Setup
Requirements: Python 3.12+, Node 26 with pnpm 12 (`npm install -g pnpm@12.15.0`, the version pinned
in `web/package.json`), Docker (for PostgreSQL and the gitleaks scanner), Git Bash on Windows for
the `scripts/*.sh`.

```bash
git config core.hooksPath .githooks          # enable the pre-commit / pre-push hooks
python -m venv .venv && .venv/bin/pip install -e ".[dev]"   # Windows: .venv/Scripts/pip
pnpm -C web install
bash scripts/devdb.sh up                     # dev/test PostgreSQL 17 on 127.0.0.1:55432
.venv/bin/garminizer demo seed               # synthetic data (dev database while there is no .env)
bash scripts/dev_api.sh                      # API on http://127.0.0.1:8425 (dev database only)
bash scripts/dev_web.sh                      # UI with hot reload on http://127.0.0.1:5180
```

The dev scripts always use the dev database and their own ports, so they never touch a real
Garminizer stack running on the same computer (8420 / 55433).

## Checks
- `bash scripts/check.sh` — the single gate: ruff, mypy (strict), pytest, eslint, prettier, tsc,
  vitest, production build, API-types freshness, UTF-8/LF, secret scan, gitleaks.
- `bash scripts/e2e.sh` — Playwright on every page in four variants (desktop/mobile × dark/light):
  charts must draw data, maps must load, no console errors, no horizontal overflow, no serious
  accessibility violations. Screenshots land in `artifacts/screenshots/`. Install the browser
  once with `pnpm -C web exec playwright install chromium`.
- After changing API models: `bash scripts/gen_api_types.sh`. After changing DB models: add an
  Alembic migration (autogenerate, then review) and run `python scripts/gen_data_model_doc.py`.

## Code style
- Backend: typed Python (mypy strict), SQL via SQLAlchemy; API responses are Pydantic models in SI
  units. Every table and important column carries a comment (it becomes `docs/data-model.md`).
- Frontend: read [`web/CONVENTIONS.md`](web/CONVENTIONS.md) — charts go through `<Chart>`, colours
  follow the validated palette (fixed sport colours, single-hue ramps, diverging for ±, status
  colours only with icon + label), one y-axis per chart, mobile first.

## Pull requests
Branch from `main` (`feat/…`, `fix/…`, `docs/…`), use conventional commit messages, keep PRs
focused, and describe how you verified the change. CI must be green.
