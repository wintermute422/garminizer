# Garminizer — instructions for Claude

Self-hosted Garmin Connect data warehouse with dashboards: Garmin Connect (unofficial API via
`garminconnect`) → PostgreSQL 17 → FastAPI → React/ECharts/MapLibre SPA. Runs locally in Docker
(`db`, `app`, `worker`). Public open-source repo: everything tracked must be generic.

## Golden rules (privacy and safety)
- **No real personal data in any tracked file, fixture, log, screenshot or commit message**: no
  names, e-mails, Garmin profile ids, GPS coordinates of real activities, hostnames, IPs, home paths,
  tokens. Fixtures are synthetic, or produced from real responses by the fixture anonymizer.
- **Never open or print `.env` or anything under `data/`** (tokens, backups, private scan values).
  Enforced by `permissions.deny` and the pre-bash hook. Credentials are typed by the user (app
  "Connect Garmin" screen or `garminizer login`), never by Claude.
- **The Garmin account is read-only.** Only whitelisted read methods are reachable through
  `garminizer.garmin.client`; a test enumerates the surface.
- **Committed screenshots come only from the demo DB** via `scripts/screenshots.sh`, which refuses a
  non-demo DB and writes `docs/screenshots/MANIFEST.sha256` (checked by pre-commit).
- **Never delete the database volume** (`docker volume rm`, `compose down -v` are blocked). Reset dev
  data with SQL or `scripts/devdb.sh reset`, which only touches the `garminizer-dev` project.
- If a secret ever lands in a commit: stop, report, tell the user to rotate it first.

## Layout
- `backend/garminizer/` Python package (config, db + migrations, models, garmin, sync, analytics,
  api, demo, worker, cli). `backend/tests/` pytest.
- `web/` React 19 + TS + Vite SPA (`src/api` generated types, `src/pages/<page>/` one dir per page).
- `scripts/` harness and dev scripts. `.githooks/` git hooks. `docs/` user docs.
- Git-ignored harness state: `plan.md`, `checks.md`, `progress.md` (repo root).

## Commands
- `bash scripts/check.sh` — the single gate (must pass before every commit).
- `.venv/Scripts/python.exe -m pytest` (Windows) / `.venv/bin/python -m pytest`.
- `bash scripts/claude_hook.sh selftest` — pre-bash rules against known good/bad commands.
- `bash scripts/secret_scan.sh --tree|--staged|--history`, `bash scripts/gitleaks.sh history`.

## Hooks and scripts
| Where | Enforces |
|---|---|
| `.claude/settings.json` PreToolUse (Bash/PowerShell) → `scripts/claude_hook.sh pre-bash` | blocks force push, push to main, `git add -A/./-f`, `--no-verify`, rebase/filter-branch, Docker volume deletion, reading `.env`/tokens/backups. Exit 2 passes through the wrapper unchanged (tested). |
| `.claude/settings.json` PostToolUse (Edit/Write) → `scripts/claude_hook.sh post-edit` | `.py`: ruff --fix, ruff format, then ruff + mypy problems fed back. `web/**`: prettier --write, eslint. |
| `.claude/settings.json` `permissions.deny` | Read/Edit of `.env`, `data/**` |
| `scripts/claude_hook.sh` / `scripts/pyenv.sh` | picks the venv interpreter (skips the Windows Store `python3` stub), execs it |
| `scripts/check.sh` | ruff, format, mypy strict, hook selftest, dev DB up, pytest, web lint/format/tsc/vitest/build, API types check, secret scan, gitleaks history |
| `scripts/secret_scan.sh` | exact values from `.env` + `data/private_values.txt` + local user name; generic rules (private IPv4, home/Windows user paths, private keys, JWTs, e-mails). Prints file:line + rule only |
| `scripts/gitleaks.sh` | gitleaks v8.30.1 (native or pinned Docker image) with `.gitleaks.toml` |
| `.githooks/pre-commit` | blocks `.env*`, `data/`, FIT/dump/key files, git-ignored files, unmanifested screenshots; ruff + prettier on staged files; secret scan + gitleaks staged |
| `.githooks/pre-push` | branches `feat/ fix/ docs/ chore/ ci/` only (main only for bootstrap), fast-forward only, no deletions, new `v*` tags only; scans the pushed range |
| `scripts/bootstrap_remote.sh` | one-time: create the private GitHub repo and push `main`; refuses once origin has `main` |
| `scripts/check_utf8.py` | every text file is UTF-8 with LF endings (pre-commit on staged files, check.sh on all) |
| `scripts/devdb.sh` | dev/test Postgres 17 (`garminizer-dev`, 127.0.0.1:55432): up/down/status/reset/psql |
| `scripts/gen_api_types.sh` | OpenAPI → `web/src/api/schema.d.ts`; `--check` fails when stale (check.sh) |
| `scripts/e2e.sh` | A9/A10: production build + FastAPI on 8421 + deterministic `garminizer_e2e` demo DB; Playwright on every page × desktop/mobile × dark/light: charts drawn with data, maps loaded, no console errors, no horizontal overflow, axe serious/critical = 0; screenshots → `artifacts/screenshots/` |
| `scripts/e2e_dev.sh API_PORT WEB_PORT "page x"` | same checks against Vite dev on private ports (parallel page work, no shared build) |

## Git workflow
- Repo-local identity `wintermute422` + GitHub noreply e-mail (never the personal address).
- Work on `feat/v1`, one commit per plan step, conventional commits. One PR to `main`; merge only
  with green CI **and** explicit user approval. Repo stays private until the user approves going public.
- Hooks are installed per clone with `git config core.hooksPath .githooks`.

## Verification rules
- Every step proves itself with real signals (tests, builds, screenshots, actual output) and gets a
  row in `checks.md`: `step | requirement | verdict | evidence` (pass / fail / unresolved).
- A failed check goes back with reason + evidence, scope "fix this step only", max 3 attempts, then
  it is reported as fail. Never relax a check, threshold or test to get a pass.
- Run checks against the saved/committed version, not against memory.

## Windows dev notes
- Interpreter: `.venv/Scripts/python.exe`. `python3` on PATH is the Microsoft Store stub (exit 49).
- Shell scripts run in Git Bash; PowerShell 5.1 has no `&&`.
- Ports: app 8420, Vite 5180, dev Postgres 55432 (127.0.0.1). 5173 and 54321–54324 belong to
  another project.

## Resuming a session
Read CLAUDE.md, `plan.md`, `progress.md`, then `git status` and `git log -5`; continue at
progress.md's "Next step".

## Lessons (append a rule whenever a mistake is caught)
- Add imports and definitions *before* (or in the same Edit as) their first use: the post-edit
  hook lints/type-checks after every single edit and reports the half-finished state.
- Edits made through shell scripts/sed bypass the post-edit hook: run `ruff format` / `ruff check`
  on the touched files right after (check.sh catches it otherwise).
- Python on Windows defaults to cp1252 and CRLF: every `read_text`/`write_text`/`open` in a
  script must pass `encoding="utf-8"` (and `newline="\n"` when writing). A cp1252 write once put
  a stray byte into CLAUDE.md and a failed write truncated checks.md. Prefer the Edit/Write tools
  for docs; use scripts only for code refactors.
- Long multi-line Python heredocs inside one Bash call can get mangled; put the script in the
  scratchpad and run it with `python -I script.py <args>`.
- Calibrate synthetic data against known physiology before building on it (check pace/HR,
  sleep-stage shares, race times vs predictions) — the first demo run had 30 % deep sleep and
  marathon HR of 183 bpm.
- Use absolute paths in every shell command: a `cd dir && …` once silently ran in the repo root
  and scattered new files there.
- React compiler lint (eslint-plugin-react-hooks 7): never write `ref.current` during render
  (update "latest" refs in an effect) and never pick a component at render time
  (`const Icon = f()`); use `createElement` (see `SportIcon`).
- ECharts 6: no `grid.containLabel` (default outerBounds already contains labels). MapLibre 6:
  pass the Vite-bundled worker via `setWorkerUrl` (see MapView), dev pre-bundling breaks it.
- e2e readiness = no `.animate-pulse` skeletons + `data-chart-ready`/`data-map-ready`; never
  `networkidle` (map tiles keep streaming).
- New pages must add every chart through `<Chart>` (it exposes data-points for the e2e "chart
  has data" check) and scrollable regions through `<ScrollArea>` (keyboard focusable, axe).
- Prove every check can fail: give each harness check a self-test or mutation. The e2e
  overflow check compared against `innerWidth`, which mobile emulation widens to fit oversized
  content, so a 590 px-wide page passed until a self-test injected a 2000 px element.
- Brief parallel agents with exact formatter paths (`prettier --write src/pages/<mine>`); a
  broad `prettier --write src/pages` touched other agents' directories.
- Never put a blocked command string literally into a shell command (even inside a JSON test
  payload): the pre-bash hook blocks the whole call. Test hook rules through pytest instead.
- Project hooks in `.claude/settings.json` take effect immediately in the running session.
- In gitleaks/secret-scan regexes use `[ \t]*`, never `\s*`, around `=`: `\s` spans the newline and
  turns an empty `KEY=` line plus the next line into a false "secret".
- Test values that look like personal data (private IPs, e-mails) are assembled at runtime in tests
  so the tracked file itself stays clean for secret_scan.
