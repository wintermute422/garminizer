# A reusable harness for agent-built projects

Garminizer was built by Claude Code inside a *harness*: files, hooks and scripts that make the
agent plan first, prove every step with a real signal, learn from its mistakes and hand over
cleanly. This folder is that harness, stripped of everything project-specific, so you can drop it
into your next project.

The idea in one line: **instructions are suggestions, hooks and scripts are rules.** Anything
that must always hold (no secrets in commits, no force pushes, formatted code, tests green) is
enforced by something that runs, not by a sentence the model might forget.

## The seven layers

| # | Layer | What it is | In this repo |
|---|---|---|---|
| 1 | Plan | Start in plan mode. A plan with inputs, steps (each with output and check), parallel marks and a completion checklist, approved by the user before work starts | [`templates/plan.md`](templates/plan.md) → `plan.md` (git-ignored) |
| 2 | Context | One `CLAUDE.md` the agent reads every session: golden rules, layout, commands, the hooks/scripts table, workflow, lessons | [`templates/CLAUDE.md`](templates/CLAUDE.md) → [`../../CLAUDE.md`](../../CLAUDE.md) |
| 3 | Hooks & scripts | Deterministic rules: Claude Code hooks (before shell commands, after edits), git hooks (pre-commit, pre-push), one gate script | `.claude/settings.json`, `scripts/claude_hook.py`, `.githooks/`, `scripts/check.sh` |
| 4 | Permissions | `permissions.deny` for secrets and private data; the pre-bash hook blocks readers of the same files | `.claude/settings.json` |
| 5 | Verification | Acceptance checks written before the work; a row per requirement with verdict and evidence, filled only from real signals against the saved version | [`templates/checks.md`](templates/checks.md) → `checks.md` (git-ignored) |
| 6 | Feedback | A failed check goes back with reason and evidence, scope "fix this step only", at most 3 attempts; every caught mistake becomes a rule under "Lessons" in `CLAUDE.md` | `CLAUDE.md` → Lessons |
| 7 | Completion | A handoff file (plan, outputs, decisions, open issues, next step) so any session can resume; deliverables and the `CLAUDE.md` diff are reported at the end | [`templates/progress.md`](templates/progress.md) → `progress.md` (git-ignored) |

## What the hooks enforce here

Copy the parts that fit your project; each one closed a real gap during this build.

- **Before every shell command** (`scripts/claude_hook.py pre-bash`, exit code 2 = blocked):
  force pushes, pushes to `main`, `git add -A/./-f`, `--no-verify`, history rewrites, Docker
  volume deletion, and any command that reads `.env`, tokens, backups or the private-values file.
  `bash scripts/claude_hook.sh selftest` runs the rule set against known good and bad commands.
- **After every edit** (`post-edit`): formatter + linter + type checker on the edited file, problems
  fed straight back to the agent.
- **pre-commit**: forbidden file names (`.env*`, data dirs, dumps, keys), git-ignored files,
  UTF-8/LF, formatters, a secret scan of the added lines (exact private values read at runtime +
  generic patterns) and gitleaks.
- **pre-push**: branch-name rules, fast-forward only, scan of the pushed range.
- **One gate** (`scripts/check.sh`): lint, format, strict types, hook self-test, tests on a
  throwaway database, frontend lint/types/unit tests/build, generated-code freshness, full-tree
  secret scan, gitleaks over history. Nothing is committed unless it is green.

## Rules that paid off

- **Write the acceptance checks before the code**, and make every check able to fail: give it a
  self-test or a mutation. (An overflow check here passed a 590 px page on a 390 px phone until
  a self-test injected a 2,000 px element.)
- **Verify against the saved version**, never against memory: rerun the gate on what is committed.
- **Parallel agents only for independent work**, each owning disjoint files, its own test
  database, its own ports and its own test-output folder. The lead integrates and re-verifies on a
  frozen build.
- **Independent review sees only the output** (screenshots, not code) and grades findings
  major/minor; majors go back, the review is repeated until none are left.
- **Private data stays out by construction**: real values live only in git-ignored files the
  scanners read at runtime; fixtures are synthetic; screenshots come from a demo database guarded
  by the screenshot script.
- **Ask before anything outward-facing or hard to undo**: publishing, merging, editing the user's
  own configuration, relaxing a check.

## Using it in a new project

1. Copy `templates/*` to the new repo root (`CLAUDE.md` tracked; `plan.md`, `checks.md`,
   `progress.md` git-ignored).
2. Copy and adapt `scripts/claude_hook.py` + `scripts/claude_hook.sh`, `.claude/settings.json`,
   `.githooks/`, `scripts/secret_scan.sh`, `scripts/gitleaks.sh` + `.gitleaks.toml`,
   `scripts/check_utf8.py`, and write your own `scripts/check.sh`.
3. `git config core.hooksPath .githooks`, run `bash scripts/claude_hook.sh selftest`.
4. Start Claude Code in plan mode with your task and the inputs table from `templates/plan.md`.
