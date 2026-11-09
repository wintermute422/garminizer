# FAQ

**Is this an official Garmin product?**
No. Garminizer uses the community library `garminconnect`, which talks to Garmin Connect's private
web API with your own login. Garmin may change that API at any time; when login breaks, updating
the library usually fixes it.

**Does Garminizer store my Garmin password?**
No. You sign in once; only Garmin's OAuth tokens are kept in `data/tokens`. If you want unattended
re-login after the tokens expire, you can optionally put `GARMIN_EMAIL`/`GARMIN_PASSWORD` in `.env`.

**My account uses two-factor authentication.**
Supported: the login asks for the code Garmin sends you.

**How long does the first sync take?**
The worker first syncs recent days, then walks back through your whole history in 10-minute chunks
with a pause between requests — a few hours for several years of data. Dashboards fill up as it goes.
Progress is on *Sync & settings*.

**My computer was off for a week.**
The worker catches up on start.

**Some charts are empty.**
They depend on your devices: HRV, SpO2, body battery, training readiness, power, running dynamics
and blood pressure only exist if your watch/scale/cuff records them.

**Can I query the data myself?**
Yes — that's the point. Connect any SQL client to `127.0.0.1:55433` (database and user
`garminizer`, the password is `POSTGRES_PASSWORD` from your `.env`, schema `garmin`).
[docs/data-model.md](data-model.md) describes every table; `garmin.v_daily` has one row per day
with all daily metrics.

**How do I get my data out?**
`docker compose exec worker garminizer backup create` writes a complete `pg_dump` to
`data/backups`. Original FIT files are in `garmin.activity_file`, raw Garmin JSON in
`garmin.raw_payload`.

**Can I try it without a Garmin account?**
Yes: `docker compose -f compose.demo.yml up -d --build` starts a separate demo on
http://localhost:8430 with two years of synthetic data (see [installation](installation.md#try-the-demo-first)).
It has its own database; Garminizer never mixes demo and real data.

**Does it run on a Raspberry Pi or a NAS?**
Anything that runs Docker Compose 2.24+ should work. It is tested on x86-64 Windows (Docker
Desktop) and Linux (CI); reports from macOS and ARM boards are welcome.

**Imperial units?**
Toggle `km`/`mi` in the top bar (defaults to your Garmin unit setting).
