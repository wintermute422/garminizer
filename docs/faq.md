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
Yes — that's the point. Connect any SQL client to `127.0.0.1:55433` (database `garminizer`, schema
`garmin`). [docs/data-model.md](data-model.md) describes every table; `garmin.v_daily` has one row
per day with all daily metrics.

**How do I get my data out?**
`garminizer backup create` writes a complete `pg_dump`. Original FIT files are in
`garmin.activity_file`, raw Garmin JSON in `garmin.raw_payload`.

**Can I try it without a Garmin account?**
Yes: `garminizer demo seed` fills a database with two years of synthetic data. Use a separate
database for your real data — Garminizer refuses to mix them.

**Imperial units?**
Toggle `km`/`mi` in the top bar (defaults to your Garmin unit setting).
