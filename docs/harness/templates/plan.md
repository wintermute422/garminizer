# <Project> — plan (vN)

## Context
Why this exists, what the user asked for, the intended outcome. Two short paragraphs.

## Inputs
| Field | Value |
|---|---|
| Task | |
| Deliverable / output | where it lives, how it is opened |
| Acceptance checks | A1–An below |
| Sources | libraries (pinned versions), APIs, sibling projects to reuse |
| Allowed changes (scope) | which folders, services, accounts may change — and what may not |
| Run limit | e.g. quality-driven; max 3 fix attempts per failed check |

## Environment facts
| Where | Found | Consequence |
|---|---|---|
| Tools | versions on this machine | |
| Ports | ports already in use | the ports this project uses |
| Permissions | permission mode | rules enforced by hooks, not trust |

## Key decisions
- Runtime, data model, frontend, security, git workflow, harness files.

## Acceptance checks (written before the work)
| # | Requirement | Evidence |
|---|---|---|
| A1 | the gate script is green | exit 0 + log tail |
| A2 | | |

## Steps
`∥` = can run in parallel with the others in the same group. Each step: output → check.

| # | Output | Reads → Writes | Check |
|---|---|---|---|
| S0 | Harness bootstrap (CLAUDE.md, hooks, scripts, settings, git) | → root | hook self-tests; gate green on the skeleton |
| S1 | | | |
| **G1 (∥ after S1)** | | | |
| S2 ∥ | | | |

## Harness enforcement (deterministic, not instructions)
- Claude hooks: …
- permissions.deny: …
- git hooks: …
- CI repeats the gate.

## Correction & memory
Failed check → back with reason, evidence, scope "fix this step only"; max 3 attempts, then
reported as fail. Never relax a check to pass. Every caught mistake becomes a rule in CLAUDE.md.

## Completion checklist
- [ ] Every output in the Steps table exists and opens (paths in progress.md)
- [ ] Every acceptance check has a verdict + evidence in checks.md, run against the committed version
- [ ] Failures fixed or listed as fail/unresolved with evidence
- [ ] CLAUDE.md reflects all hooks, scripts and lessons; diff reported
- [ ] Anything outward-facing (publish, merge) only after the user's yes

## What I need from you
1. …
