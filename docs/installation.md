# Installation

Garminizer runs as three Docker containers on your own computer: a PostgreSQL 17 database, the
web app and a background worker that syncs with Garmin Connect. Setting it up takes about ten
minutes plus the first image build.

- [1. Requirements](#1-requirements)
- [2. Get the code](#2-get-the-code)
- [3. Create your settings file](#3-create-your-settings-file)
- [4. Start Garminizer](#4-start-garminizer)
- [5. Connect your Garmin account](#5-connect-your-garmin-account)
- [6. The first sync](#6-the-first-sync)
- [Start with your computer](#start-with-your-computer) · [Update](#update) ·
  [Stop and uninstall](#stop-and-uninstall) · [Troubleshooting](#troubleshooting)

Just want to look around first? The [demo](#try-the-demo-first) needs no Garmin account.

## 1. Requirements

| | |
|---|---|
| **Docker** | [Docker Desktop](https://www.docker.com/products/docker-desktop/) on Windows 10/11 and macOS, or Docker Engine with the Compose plugin on Linux. Compose **2.24 or newer** (`docker compose version`). On Windows, Docker Desktop sets up WSL 2 for you. |
| **Git** | to download and update the code ([git-scm.com](https://git-scm.com/downloads)). |
| **Disk** | about 2 GB for the images and build cache, plus your data: typically well under 1 GB, even for many years of activities with second-by-second samples. |
| **A Garmin Connect account** | the one your watch syncs to. Two-factor authentication is supported. |

Python is optional: it only makes step 3 a one-liner.

All commands below run in a terminal (PowerShell on Windows, Terminal on macOS/Linux) inside the
`garminizer` folder. Where Windows differs, it is shown separately.

## 2. Get the code

```bash
git clone https://github.com/wintermute422/garminizer.git
cd garminizer
```

## 3. Create your settings file

Your settings live in a file called `.env` in the `garminizer` folder. It holds your database
password, so it is never committed and stays on your computer.

**With Python** (recommended): creates `.env` with a random database password and session key.
Put your [time zone](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) after `--tz`.

```bash
python3 scripts/init_env.py --tz Europe/Berlin     # macOS / Linux
```
```powershell
py scripts/init_env.py --tz Europe/Berlin          # Windows (or: python scripts/init_env.py ...)
```

**Without Python**: copy the template and edit it.

```bash
cp .env.example .env
```

Open `.env` in any text editor (`notepad .env` on Windows, `nano .env` or `open -e .env` on
macOS/Linux) and set:

| Setting | Set it to |
|---|---|
| `POSTGRES_PASSWORD` | a long random password (letters and digits; you will rarely need it) |
| `DATABASE_URL` | replace `change-me` in it with the same password (only used by command-line tools outside Docker) |
| `TZ` | your time zone, e.g. `Europe/Berlin` or `America/New_York` |

Everything else can stay as it is; [configuration](configuration.md) explains every setting.

## 4. Start Garminizer

```bash
docker compose up -d --build
```

The first run builds the image (5–10 minutes, depending on your computer and connection) and then
starts the database, app and worker. Check that all three are up:

```bash
docker compose ps
```

`db` and `app` should be `Up … (healthy)`, `worker` `Up`. Then open
**[http://localhost:8420](http://localhost:8420)**.

## 5. Connect your Garmin account

In the app, open **Sync & settings**, enter your Garmin e-mail and password under **Garmin
connection** and click **Connect Garmin**. If your account uses two-factor authentication, Garmin
sends you a code; enter it when the app asks for it.

Garminizer does not store your password: Garmin hands out login tokens, which are saved in
`data/tokens` and renewed automatically. Prefer the terminal? This does the same:

```bash
docker compose exec app garminizer login
```

## 6. The first sync

The worker starts right after you connect. It fetches the last days first, so the dashboards show
today's data within minutes, and then works backwards through your whole history in short,
polite batches. For several years of data this takes a few hours; the dashboards fill up as it
goes. Progress and history coverage are shown on **Sync & settings**. To watch the log:

```bash
docker compose logs -f worker
```

(Ctrl+C stops watching; the worker keeps running.) After that, the worker syncs every two hours
and writes a nightly backup to `data/backups` at 03:30 your time.

That's it. Next steps:
- open the dashboards from your phone: [phone access on your network](configuration.md#phone-access-on-your-network)
- query your data with SQL: [data model](data-model.md)
- log meals with Claude Desktop: [Claude Desktop guide](claude-desktop.md)

## Start with your computer

The containers restart on their own whenever Docker runs. On Windows and macOS, enable
**Docker Desktop → Settings → General → Start Docker Desktop when you sign in to your
computer**. On Linux, enable
the Docker service: `sudo systemctl enable docker`. If your computer was off for a while, the
worker catches up on start.

## Update

Back up, pull the new version and rebuild. Database migrations run automatically when the app
starts.

```bash
docker compose exec worker garminizer backup create
git pull
docker compose up -d --build
```

Release notes are in the [commit history](https://github.com/wintermute422/garminizer/commits/main).

## Stop and uninstall

```bash
docker compose stop        # stop; start again with: docker compose start
docker compose down        # remove the containers; your data stays in the database volume
```

To remove Garminizer **and all your data**, first copy any backups you want to keep out of
`data/backups`, then run `docker compose down --volumes --rmi all` and delete the `garminizer`
folder. This deletes the database permanently.

## Try the demo first

```bash
docker compose -f compose.demo.yml up -d --build
```

Open **[http://localhost:8430](http://localhost:8430)**: two years of a simulated athlete (the
first start needs a minute or two to generate them). The demo has its own database, port and
containers and never touches your real data. Remove it with
`docker compose -f compose.demo.yml down --volumes`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `required variable POSTGRES_PASSWORD is missing` / `set POSTGRES_PASSWORD in .env` | `.env` is missing or has no password; see [step 3](#3-create-your-settings-file). Run the commands inside the `garminizer` folder. |
| An error about `env_file` (`path` / `required` not allowed) | Your Docker Compose is too old; update Docker Desktop or the Compose plugin to 2.24+. |
| `port is already allocated` / `address already in use` | Another program uses 8420 (app) or 55433 (database). Set `APP_PORT=8421` or `DB_PORT=55434` in `.env` and run `docker compose up -d` again. |
| `localhost:8420` does not load | `docker compose ps` shows the state; `docker compose logs app` shows why the app is not healthy. |
| Login fails although the password is right | Garmin changes its login from time to time. Update Garminizer (see [Update](#update)); the new version usually ships a fixed `garminconnect` library. |
| The sync log mentions a rate limit (HTTP 429) | Garmin asks for a pause. The worker backs off and continues by itself; don't lower `SYNC_REQUEST_DELAY_S`. |
| Some charts stay empty | They need data your devices don't record (HRV, SpO2, power, blood pressure, …). See the [FAQ](faq.md). |
| Days are cut at the wrong hour | Set `TZ` in `.env` to your time zone, then `docker compose up -d`. |

Still stuck? [Open an issue](https://github.com/wintermute422/garminizer/issues/new/choose), but
please never paste your `.env`, tokens, e-mail address or real health data.
