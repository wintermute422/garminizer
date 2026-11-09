# Development harness

Garminizer was built inside a small "harness": a plan with one check per step, deterministic
hooks and scripts instead of remembered rules, and a verification report. The pieces are reusable
for other projects.

## Deterministic rules (hooks and scripts)
| Mechanism | Enforces |
|---|---|
| `.githooks/pre-commit` | blocks `.env`, `data/`, keys, dumps, FIT files, git-ignored files and unmanifested screenshots; UTF-8/LF; ruff/prettier on staged files; exact-value + generic personal-data scan; gitleaks |
| `.githooks/pre-push` | feature branches only, fast-forward only, no deletions, scans every pushed range |
| `.claude/settings.json` | for AI-assisted development: auto-format after edits, block force pushes, history rewrites, volume deletion and reading `.env`/tokens |
| `scripts/check.sh` | the single local gate (lint, strict types, tests, web build, API types, UTF-8, secret scan, gitleaks) |
| `scripts/e2e.sh` | every page × desktop/mobile × dark/light: charts draw data, maps load, no console errors, no overflow, axe clean |
| `scripts/secret_scan.sh` | exact values read at runtime from `.env` and `data/private_values.txt` (written by the sync: your names, ids, home area) plus generic patterns, over added lines, commit messages and author/committer identities (only noreply addresses pass); prints file:line only |
| `scripts/gen_api_types.sh`, `scripts/gen_data_model_doc.py` | generated artefacts with `--check` mode so they cannot drift |

Enable the git hooks once per clone: `git config core.hooksPath .githooks`.

## Testing strategy
- **Unit tests** for every formula with hand-computed expectations (`backend/tests/test_analytics_*`).
- **Database tests** against a throwaway PostgreSQL database (migrations round-trip, models match
  migrations, every table documented, pipeline idempotent, demo generator deterministic).
- **API contract test** walks every GET endpoint from the OpenAPI schema on a demo database and
  enforces p95 < 300 ms.
- **Sync tests** use a fake Garmin client and synthetic fixtures (rate limits, crashes mid-backfill,
  read-only whitelist).
- **End-to-end** Playwright tests on the production build.

## Demo data for screenshots
Screenshots in the README come from `scripts/e2e.sh` runs on the deterministic demo database
(`garminizer_e2e`, seed 42) — never from real data.
