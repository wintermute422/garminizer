# Changelog

All notable changes to Garminizer are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). Each release is published as a container image
(`ghcr.io/wintermute422/garminizer:<version>`) for x86-64 and ARM64.

## [0.1.0] - 2026-11-16

First public release.

### Sync and storage
- Read-only sync of a Garmin Connect account into PostgreSQL 17 on your own computer:
  activities at full resolution from the original FIT files, sleep, HRV, stress, Body Battery,
  heart rate, SpO2, respiration, steps, training readiness and status, VO2max, race predictions,
  endurance and hill score, body composition, blood pressure, gear, devices and personal records.
- Sign-in with two-factor support; only Garmin's tokens are stored, never the password.
- The last days are synced first, then the whole history in polite batches; every Garmin
  response is kept verbatim so parsers can be improved without downloading again.
- Sync every two hours, hourly quick sync of new activities and weigh-ins, nightly backups with
  restore, and a `verify` command that compares the database with Garmin.
- Documented SQL schema (about 45 tables and views) for your own queries.

### Dashboards
- 16 dashboards: overview, activities, activity detail, training load, performance, records,
  health and recovery, sleep, body, nutrition, weight goal, calendar, map, insights, gear and
  year in review.
- Dark and light themes, metric and imperial units, phone layout, every view shareable by URL.
- First-run welcome screen with the Garmin sign-in and the progress of the first sync.

### Nutrition and weight goal
- Meal logging through Claude Desktop over the Model Context Protocol, compared with Garmin's
  calorie burn.
- Weight goal with a weighted trend, weekly checkpoints and a daily energy balance.

### Running it
- Docker Compose stack (database, app, worker) bound to this computer by default; optional
  password-protected access from your network.
- Demo stack with two years of a synthetic athlete, no Garmin account needed.

[0.1.0]: https://github.com/wintermute422/garminizer/releases/tag/v0.1.0
