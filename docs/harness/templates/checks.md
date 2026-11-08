# checks.md — verification report

Verdicts: pass / fail / unresolved. Evidence is a command + result or a path. Rows are only set
to pass from a real signal run against the saved version.

## Acceptance checks
| step | requirement | verdict | evidence |
|---|---|---|---|
| S? | A1 gate script green (all stages) | unresolved | |

## Step checks
| step | requirement | verdict | evidence |
|---|---|---|---|
| S0 | hook self-test: blocked/allowed command sets | unresolved | |
| S0 | pre-commit blocks secrets, ignored files, non-UTF-8/CRLF | unresolved | |
