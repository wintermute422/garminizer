# Configuration & operations

All settings come from environment variables or the git-ignored `.env` file, created during
[installation](installation.md#3-create-your-settings-file) from [`.env.example`](../.env.example).
After changing `.env`, apply it with `docker compose up -d`.

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_PASSWORD` | — (required for Docker) | password of the bundled database |
| `DB_PORT` | `55433` | host port of the database (bound to 127.0.0.1) |
| `DATABASE_URL` | dev DB | used by the CLI outside Docker; any PostgreSQL ≥ 14 works |
| `APP_HOST` | `127.0.0.1` | who may reach the dashboard. `0.0.0.0` = your LAN (requires `APP_PASSWORD`) |
| `APP_PORT` | `8420` | dashboard port on your computer |
| `APP_PASSWORD` | empty | login password; required whenever `APP_HOST` is not loopback |
| `APP_SECRET_KEY` | generated | signs session cookies (stored in the DB when empty) |
| `GARMIN_EMAIL`, `GARMIN_PASSWORD` | empty | optional, only for unattended re-login when tokens expire |
| `SYNC_INTERVAL_HOURS` | `2` | incremental sync interval of the worker |
| `QUICK_SYNC_MINUTES` | `60` | quick sync of new activities and weigh-ins only (weight goal, energy balance); `0` turns it off |
| `SYNC_REQUEST_DELAY_S` | `1.0` | minimum pause between Garmin requests (be kind; don't lower it much) |
| `BACKUP_KEEP` | `14` | number of nightly backups kept in `data/backups` |
| `TZ` | `UTC` | your time zone (backup time; daily boundaries when Garmin has not sent one for your profile) |
| `GARMINIZER_DATA` | `./data` | host folder for tokens and backups (Docker) |
| `MAP_STYLE_URL`, `MAP_STYLE_URL_DARK` | OpenFreeMap positron / dark | MapLibre style URLs |
| `DEMO_PORT` | `8430` | port of the demo stack (`compose.demo.yml`) |

## Common tasks
Run these inside the `garminizer` folder (PowerShell, Terminal or any shell):

```bash
docker compose up -d --build              # start / update
docker compose logs -f worker             # watch syncing
docker compose exec worker garminizer sync          # sync now
docker compose exec worker garminizer verify        # compare DB with Garmin
docker compose exec worker garminizer backup create # backup now
docker compose exec worker garminizer backup list
docker compose exec worker garminizer backup restore /data/backups/<file> --yes
docker compose exec worker garminizer reparse       # rebuild typed tables from raw payloads
docker compose exec worker garminizer analytics refresh --force
docker compose down                       # stop (keeps your data)
```
Never run `docker compose down -v` unless you want to delete the database volume.

## Phone access on your network
Set `APP_HOST=0.0.0.0` and a strong `APP_PASSWORD` in `.env`, then `docker compose up -d`. Open
`http://<your-computer's-LAN-address>:8420` on the phone. Do not forward the port to the internet;
use a VPN (e.g. WireGuard/Tailscale) for remote access.

## Using your own PostgreSQL server
Create a database and role, point `DATABASE_URL` at it, then run `garminizer db upgrade` and start
`garminizer serve` and `garminizer worker` (or adapt `compose.yml` and remove the `db` service).
