# Meal logging with Claude Desktop

Garminizer keeps a food diary next to your Garmin data. You give the meals to **Claude Desktop**
(a photo, or a sentence like "two eggs on toast and a latte"); Claude recognises the foods,
estimates portions, calories and macros, and hands the numbers to your local Garminizer through
the **Model Context Protocol (MCP)**. Garminizer stores them and answers with your day so far:
intake against your targets, what is left, and the calories Garmin measured you burning.

```
photo / text ──▶ Claude Desktop ──(MCP over stdio)──▶ garminizer mcp ──▶ your PostgreSQL
                 estimates foods,                      validates, stores,   meal, meal_item
                 grams, kcal, macros                   answers day summary
```

Garminizer does no image recognition itself and calls no outside service; the estimate is
Claude's. The dashboards then compare intake with Garmin's energy expenditure (balance =
intake − Garmin's total kcal of the day).

## 1. Connect Claude Desktop

Open the config file: in Claude Desktop **Settings → Developer → Edit Config**, or directly

| System | File |
|---|---|
| Windows (installer) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Windows (Microsoft Store / MSIX app) | `%LOCALAPPDATA%\Claude-Data\<package folder>\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |

**Edit Config** always opens the right file, so use it when unsure.

Add a `garminizer` entry under `mcpServers` (keep any servers you already have), save, and
**restart Claude Desktop** completely (quit it from the tray / menu bar, not just the window).

### Option A: Garminizer runs in Docker (recommended)

```json
{
  "mcpServers": {
    "garminizer": {
      "command": "docker",
      "args": ["exec", "-i", "garminizer-app-1", "garminizer", "mcp"]
    }
  }
}
```

- `garminizer-app-1` is the app container of the standard `docker compose up -d` stack. Check
  the name with `docker ps --format "{{.Names}}"`; the demo stack (`compose.demo.yml`) is
  `garminizer-demo-app-1`.
- Keep `-i` (Claude talks to the server over stdin) and do **not** add `-t`: a terminal would
  garble the protocol.
- The container must be running when Claude Desktop starts. Docker Desktop puts `docker` on the
  `PATH`; if Claude cannot find it, use the full path, e.g.
  `"C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe"` on Windows or
  `"/usr/local/bin/docker"` on macOS.
- Inside the container the server already knows the database and your `TZ`.

### Option B: a local Python install (development checkout)

```json
{
  "mcpServers": {
    "garminizer": {
      "command": "C:\\path\\to\\garminizer\\.venv\\Scripts\\garminizer.exe",
      "args": ["mcp", "--env-file", "C:\\path\\to\\garminizer\\.env"]
    }
  }
}
```

On macOS/Linux the command is `/path/to/garminizer/.venv/bin/garminizer`. Claude Desktop starts
the server outside the Garminizer folder, so `--env-file` tells it where your `.env` is: its
`DATABASE_URL` (by default `127.0.0.1:55433`, the Docker database) and `TZ` are used. Without
`--env-file` or a `DATABASE_URL` environment variable the server falls back to the development
database and says so in its log. You could also put `"env": {"DATABASE_URL": "..."}` into the
config instead, but that copies your database password into Claude's config file.

### Check the connection

After the restart, Claude Desktop lists `garminizer` under **Settings → Developer** as running,
and the tools menu in the chat box shows its tools. If it shows an error, see
[Troubleshooting](#troubleshooting).

## 2. Use it

Just talk to Claude; it decides when to call the tools. Examples:

- *"Log this lunch"* + a photo of your plate.
- *"Breakfast at 7:15: porridge with 60 g oats, milk, a banana and a spoon of peanut butter."*
- *"I had a 0.5 l beer and a handful of crisps at 21:00."*
- *"What did I eat today versus what I burned?"*
- *"How was my protein this week? I weigh about 72 kg."*
- *"Yesterday's dinner was a bigger portion, about 150 g more pasta. Fix it."*
- *"I ran 30 km this morning. How much should I eat for the rest of the day?"*
- *"Set my targets: 2,700 kcal and 1.8 g protein per kg."*

Claude Desktop also offers the prompt **log-meal-from-photo** (the "+" / attachment menu →
Garminizer) with the estimation procedure built in: attach the photo and pick it.

Claude asks for permission the first time it uses a tool; you can allow it once or always.

### Tools

| Tool | What it does |
|---|---|
| `log_meal` | Store a meal: name, items (food, portion in g, kcal, protein, carbs, fat, fibre), time, type, notes, confidence. Totals are the sum of the items; returns the meal, warnings and the day so far |
| `get_day_nutrition` | All meals of a day with items, totals, targets and what is left, Garmin's burn, balance |
| `list_recent_meals` | Meals of the last days (with `meal_id`), grouped by day |
| `update_meal` | Correct a meal (new items replace the old ones and recompute the totals) |
| `delete_meal` | Remove a meal logged by mistake |
| `get_nutrition_targets` / `set_nutrition_targets` | Daily targets: kcal, protein (g or g per kg body weight), carbs, fat, fibre |
| `get_energy_context` | Garmin's view of a day: calories burned, activities, training load, readiness |

Times are your local time (the athlete time zone from Garmin, else `TZ`); a meal belongs to the
local calendar day it was eaten. When the macros do not add up to the calories
(4 × protein + 4 × carbs + 9 × fat + 7 × alcohol off by more than 15 %) the meal is stored with a
`macro_kcal_mismatch` warning so Claude can double-check it.

### How good are the numbers?

Photo estimates are typically within 20–30 % for a whole meal; hidden fat (oil, butter,
dressing) is the biggest source of error, which is why Claude is told to ask about it and to note
its assumptions. Garmin's calorie burn is an estimate too. Use the balance as a trend over weeks
rather than a verdict on one day. For better numbers: mention weights you know, photograph the
package label, or say "about a fist of rice".

## 3. In the dashboard and in SQL

Meals appear in Garminizer's nutrition views and in the insights correlations
(`intake_kcal`, `protein_g`, `energy_balance_kcal` in `garmin.v_daily`). The API is under
`/api/nutrition` (`/daily`, `/summary`, `/day`, `/meals`, `/targets`). Tables: `garmin.meal`,
`garmin.meal_item` ([data model](data-model.md#nutrition)).

## Privacy

- Your food diary is stored only in your own Garminizer database, on your computer.
- The MCP server runs locally (inside your Garminizer container or venv) and talks only to
  Claude Desktop on the same computer and to your database. It opens no network port and sends
  nothing anywhere itself.
- Photos and messages you give Claude are processed by Anthropic's Claude service as part of
  your conversation, like any other chat. The tool results (for example today's meals, Garmin
  calories and activities) become part of that conversation too. If you don't want certain
  data in a chat, don't ask Claude about it.
- Meals are your own input, so they are logged even when Garminizer holds demo data (they are
  marked `source = claude`; demo meals are `source = demo`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Server disconnected" / garminizer not listed | Is the container running (`docker ps`)? Does the name match? Restart Claude Desktop after every config change |
| `docker` not found | Use the full path to `docker.exe` / `docker` in `command` |
| Tool error "database is not reachable" | Start Garminizer (`docker compose up -d`), or check `DATABASE_URL` in the `--env-file` |
| Meals land on the wrong day | Set your time zone: Garmin profile, or `TZ` in `.env` |
| Look at the server log | Windows: `%APPDATA%\Claude\logs\mcp-server-garminizer.log`; macOS: `~/Library/Logs/Claude/mcp-server-garminizer.log` |

You can test the server by hand: `docker exec -i garminizer-app-1 garminizer mcp` waits silently
for JSON-RPC on stdin (stop it with Ctrl+C); its log lines go to stderr. Garminizer never edits
your Claude Desktop configuration; you add the entry yourself.
