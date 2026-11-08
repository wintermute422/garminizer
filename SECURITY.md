# Security

## Reporting a vulnerability
Please report security problems privately via
[GitHub security advisories](https://github.com/wintermute422/garminizer/security/advisories/new),
not as public issues. You will get an answer within a few days.

## How Garminizer protects your data
- **Local by default.** The app, database and worker run on your own computer. The web app binds to
  `127.0.0.1`; exposing it to your network (`APP_HOST=0.0.0.0`) requires `APP_PASSWORD`, otherwise
  it refuses to start. Sessions use signed, HttpOnly, SameSite=Strict cookies; logins are rate
  limited; state-changing requests need a CSRF header.
- **Your Garmin password is not stored.** You sign in once (in the app or with `garminizer login`);
  only Garmin's OAuth tokens are kept in `data/tokens` (created with owner-only permissions where the
  file system supports it). `garminizer logout` deletes them; revoke sessions in your Garmin account
  if a token file may have leaked.
- **Read-only access.** Garminizer only calls read endpoints of Garmin Connect.
- **Nothing leaves your machine** except requests to Garmin Connect and map tiles from the
  configured tile server (OpenFreeMap by default; tile requests reveal the map area you look at).
- **Backups** (`data/backups`) contain all your data — store copies safely.

## Unofficial API
Garminizer uses the community library [`garminconnect`](https://github.com/cyberjunky/python-garminconnect),
which talks to Garmin Connect's private web API. It is not affiliated with or endorsed by Garmin and
can break when Garmin changes its login or endpoints. Keep the default request rate; aggressive
syncing can get an account rate-limited.

## Supported versions
Security fixes go into the latest release.
