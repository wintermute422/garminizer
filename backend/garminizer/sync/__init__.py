"""Garmin sync: raw-first storage, parsers into the typed tables, incremental/backfill engine.

Modules: `datasets` (registry of what is fetched and how it is parsed), `parsers` (Garmin JSON →
row operations), `store` (raw payloads + row writer), `fit` (original FIT files → samples),
`engine` (incremental, backfill, reparse, locking), `verify`, `private_values`.
"""
