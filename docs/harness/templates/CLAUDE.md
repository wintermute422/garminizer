# <Project> — instructions for Claude

One paragraph: what this is and how it runs.

## Golden rules (privacy and safety)
- No real personal data in any tracked file, fixture, log, screenshot or commit message.
- Never open or print `.env` or private data folders (enforced by `permissions.deny` and the
  pre-bash hook). Credentials are typed by the user, never by Claude.
- Never delete data you cannot recreate (blocked by the pre-bash hook).
- If a secret ever lands in a commit: stop, report, tell the user to rotate it first.

## Layout
- Where the code, tests, scripts, hooks and docs live.
- Git-ignored harness state: `plan.md`, `checks.md`, `progress.md`.

## Commands
- `bash scripts/check.sh` — the single gate (must pass before every commit).

## Hooks and scripts
| Where | Enforces |
|---|---|
| `.claude/settings.json` PreToolUse → `scripts/claude_hook.sh pre-bash` | blocked commands (exit 2) |
| `.claude/settings.json` PostToolUse → `scripts/claude_hook.sh post-edit` | format + lint + types after every edit |
| `.claude/settings.json` `permissions.deny` | reads/edits of secrets and private data |
| `.githooks/pre-commit` | forbidden files, formatting, encoding, secret scan of added lines |
| `.githooks/pre-push` | branch rules, fast-forward only, scan of the pushed range |
| `scripts/check.sh` | every stage of the gate |

## Git workflow
- Feature branch, one commit per plan step, conventional commits; merge only with green CI and
  the user's approval.

## Verification rules
- Every step proves itself with real signals and gets a row in `checks.md`
  (`step | requirement | verdict | evidence`).
- Failed check → reason + evidence, "fix this step only", max 3 attempts, then reported as fail.
  Never relax a check, threshold or test to get a pass.
- Run checks against the saved/committed version, not against memory.

## Resuming a session
Read CLAUDE.md, `plan.md`, `progress.md`, then `git status` and `git log -5`; continue at
progress.md's "Next step".

## Lessons (append a rule whenever a mistake is caught)
- …
