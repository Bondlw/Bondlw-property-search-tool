# Property Search Tool — Workflow & Operations Guide

## Daily Pipeline Overview

The tool runs a four-step pipeline every morning at 7:00 AM via Windows Task Scheduler. Each step can also be run independently via the CLI.

```
Step 1: Search      — Scrape Rightmove listings for each configured area
Step 2: Detail      — Fetch full listing pages for new/incomplete properties
Step 3: Enrich      — Pull crime data, supermarket distances, commute times
Step 4: Report      — Run all hard gates, score properties, generate HTML report
                      → Windows toast notification + email (if configured)
                      → Report auto-opens in default browser
```

---

## Step-by-Step Pipeline Detail

### Step 1: Search (`src/scrapers/rightmove_scraper.py`)

For each configured area (Tunbridge Wells, Southborough, Paddock Wood, Marden, Staplehurst), the scraper hits the Rightmove search API and extracts all listing summaries from the embedded `PAGE_MODEL` JSON. Each listing yields: price, address, postcode, property type, Rightmove listing ID.

For each listing:

- If it does not exist in the DB → insert it (new property; price history entry created).
- If it already exists and the price has changed → update price, set `price_reduced` flag, add a price history entry.
- If it already exists with the same price → update `last_seen_date` only (confirms still active).

Properties not seen during a scrape are not immediately marked inactive — they are simply not updated. The `is_active` flag is only cleared manually or by a separate deactivation step.

### Step 2: Detail Fetch (`src/scrapers/rightmove_scraper.py`)

The repository query `get_properties_needing_details` returns all active properties that have no description or no images. The scraper fetches each individual listing page and extracts:

- Tenure (freehold / leasehold / share of freehold)
- Lease years remaining
- Service charge (£/yr) and ground rent (£/yr)
- Council tax band and EPC rating
- Full description and key features
- Floorplan URLs, images, video, brochure
- Room dimensions
- Nearest train stations (name, distance in metres, walk minutes) — stored immediately into `enrichment_data`
- Agent name, coordinates (lat/lng), first listed date

`update_property_details` uses a selective update — only non-null fields from the scraped listing overwrite existing DB values. This means a re-fetch never erases data that was already stored.

### Step 3: Enrichment (`src/enrichment/enrichment_service.py`)

The repository query `get_properties_needing_enrichment` returns active properties that have coordinates but no crime data. For each:

1. **Crime** — queries `data.police.uk/api/crimes-at-location` with the property's lat/lng. Tries the last 3 months in reverse order; uses the first successful response. Stores a normalised summary: `{asb, burglary, drugs, violent, vehicle, total, month}` as JSON.

2. **Supermarkets** — queries Nominatim (OpenStreetMap) for each major chain within a 5 km bounding box. Stores the nearest of any chain as `nearest_supermarket_*`, and Lidl/Aldi individually for backwards compatibility. Nominatim enforces a 1 req/s rate limit; the service sleeps 1.1 s between requests.

3. **Commute** — a pure config lookup (no API). Matches the property's nearest station name (from Step 2) or postcode district to the `commute_lookup` table. Returns `commute_to_london_min`, `commute_to_maidstone_min`, `annual_season_ticket`.

All enrichment data is upserted, not replaced — existing fields survive partial updates.

### Step 4: Report Generation (`src/reporting/report_generator.py`)

All active properties are loaded from the DB along with their enrichment data and price history. For each property:

1. Hard gates are evaluated (`check_all_gates`). All 15+ gate results are collected.
2. Properties that pass all gates are scored (0–100) using the weighted scoring engine.
3. Financial calculations are run: monthly mortgage + SC + GR + council tax + bills, affordability rating (green/amber/red), recommended offer price, deposit recommendation.
4. Properties are classified into sections:
   - **Qualifying** — all gates pass, GREEN monthly cost
   - **Favourites** — user-starred, shown regardless of gate status
   - **Opportunities** — near-budget misses where a negotiated offer would qualify (on market 30+ days)
   - **Near Misses** — failed gates not appearing in Opportunities, sorted by gate severity
   - **New Today** — first seen date = today
5. The Jinja2 template (`templates/daily_report.html`) is rendered and written to `output/reports/report_YYYY-MM-DD.html`.
6. Notifications are sent (toast + email if configured).
7. The report is opened in the default browser.

---

## CLI Commands

All commands are run from the project directory:

```
cd "C:\Users\liam.bond\Documents\Property Search Tool"
python -m src <command>
```

### `run` — Full Pipeline

```bash
python -m src run
```

Runs all four steps in sequence: search → detail → enrich → report. This is what Task Scheduler executes daily.

Options:

```bash
python -m src run --portal rightmove   # Portal to search (default: rightmove)
python -m src run --area "Paddock Wood"  # Search one area only
python -m src run --skip-detail        # Skip detail fetch and enrichment; search + report only
```

### `search` — Scrape Only

```bash
python -m src search
python -m src search --area "Tunbridge Wells"
```

Scrapes Rightmove listings and updates the DB. Does not fetch details, enrich, or generate a report.

### `detail` — Fetch Listing Details

```bash
python -m src detail
python -m src detail --limit 20        # Process at most 20 properties
```

Fetches full listing pages for all active properties missing description/images. Prints tenure, lease, and nearest station for each property processed.

### `enrich` — Enrich Properties

```bash
python -m src enrich
python -m src enrich --limit 10
```

Runs the enrichment service for all properties with coordinates but no crime data. Prints crime count, Lidl/Aldi walk times, and Maidstone commute for each property.

### `report` — Generate Report Only

```bash
python -m src report
```

Generates a fresh HTML report from the current DB state. No scraping or enrichment. Useful for regenerating after adjusting config or exclusions. Opens in browser automatically.

### `serve` — Interactive Web UI

```bash
python -m src serve
python -m src serve --port 9000        # Custom port (default: 8765)
```

Starts a local HTTP server at `http://localhost:8765`. Opens the latest report in the browser. The server enables the interactive buttons on each property card (favourite, exclude, add note, book viewing, send enquiry). All actions persist to the database immediately.

The server also exposes `/api/regenerate` — clicking "Regenerate" in the browser re-runs the report generator in-process, so the page refreshes with any changes (e.g. newly excluded properties disappear from the report).

### `status` — Database Statistics

```bash
python -m src status
```

Prints a summary of the database: total properties, active count, new today, price reductions, exclusions. Includes a per-postcode-area breakdown (average, min, max price) and the last 5 pipeline runs with timing and error counts.

### `areas` — List Configured Search Areas

```bash
python -m src areas
```

Prints all configured search areas with their Rightmove IDs and area type (primary/secondary).

### `exclude` — Manage Exclusions

```bash
# Exclude a property
python -m src exclude add 42 "Leasehold with high service charge"

# Remove an exclusion
python -m src exclude remove 42

# List all exclusions
python -m src exclude list
```

Exclusions are stored in the DB and applied on the next report generation. Excluded properties are hidden from qualifying, near-miss, and opportunities sections.

### `backfill-stations`

```bash
python -m src backfill-stations
python -m src backfill-stations --limit 50
```

Re-fetches station data for enriched properties that are missing nearest station information. Useful after a failed detail fetch run.

### `init` — Initialise Database

```bash
python -m src init
```

Creates the database file and initialises all tables. Safe to re-run — all `CREATE TABLE` statements use `IF NOT EXISTS`.

---

## Windows Task Scheduler

The daily run is registered as a Windows Scheduled Task named `PropertySearch_DailyRun`.

**Configuration (from `scripts/setup_scheduler.ps1`):**

| Setting              | Value                                                                   |
| -------------------- | ----------------------------------------------------------------------- |
| Task name            | `PropertySearch_DailyRun`                                               |
| Command              | `python.exe -m src run`                                                 |
| Working directory    | `C:\Users\liam.bond\Documents\Property Search Tool`                     |
| Python executable    | `C:\Users\liam.bond\AppData\Local\Programs\Python\Python313\python.exe` |
| Trigger              | Daily at 7:00 AM                                                        |
| Execution time limit | 2 hours                                                                 |
| Restart on failure   | Once, after 10 minutes                                                  |
| Start when available | Yes (catches up if the PC was off)                                      |
| Log output           | `output\logs\scheduler.log`                                             |

**To register or re-register the task** (run PowerShell as Administrator):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "C:\Users\liam.bond\Documents\Property Search Tool\scripts\setup_scheduler.ps1"
```

**Useful Task Scheduler commands:**

```powershell
# Check if the task is registered
Get-ScheduledTask -TaskName "PropertySearch_DailyRun"

# Run the task immediately (triggers the full pipeline now)
Start-ScheduledTask -TaskName "PropertySearch_DailyRun"

# View last run result
(Get-ScheduledTaskInfo -TaskName "PropertySearch_DailyRun").LastTaskResult

# Remove the task
Unregister-ScheduledTask -TaskName "PropertySearch_DailyRun"
```

A result of `0` means the last run completed successfully. Any other value indicates an error.

---

## How to Manually Trigger a Run

**Option 1 — Via Task Scheduler (recommended):**

```powershell
Start-ScheduledTask -TaskName "PropertySearch_DailyRun"
```

This runs with the same environment and privileges as the scheduled run.

**Option 2 — Directly in a terminal:**

```bash
cd "C:\Users\liam.bond\Documents\Property Search Tool"
python -m src run
```

Output is printed to the terminal in real time.

**Option 3 — Just regenerate the report (no scraping):**

```bash
python -m src report
```

Useful when you have adjusted config (e.g. changed budget caps or added an exclusion) and want to see the updated report without waiting for a full scrape.

---

## Log Locations

| Log            | Location                                    | Notes                                                       |
| -------------- | ------------------------------------------- | ----------------------------------------------------------- |
| Scheduler log  | `output\logs\scheduler.log`                 | Stdout/stderr from Task Scheduler runs                      |
| Run history    | `data\property_search.db` → `run_log` table | Structured run metadata; visible via `python -m src status` |
| Console output | Terminal (when run manually)                | Live progress printed by `click.echo` and Python `logging`  |

To query the run log directly:

```bash
python -m src status
```

Or using SQLite directly:

```bash
# Open the database (requires sqlite3 CLI or DB Browser for SQLite)
sqlite3 "data/property_search.db" "SELECT * FROM run_log ORDER BY created_at DESC LIMIT 10;"
```

---

## Debugging Failures

### No properties found

1. Check internet connectivity.
2. Rightmove may have changed their page structure — check `src/scrapers/rightmove_scraper.py` and the raw HTML response.
3. Run `python -m src search` manually and observe the output.
4. Check if Rightmove IDs in `config/search_config.yaml` are still valid (`rightmove_id` per area).

### Details not fetching

1. Run `python -m src detail --limit 5` and watch the output for errors.
2. Rightmove may be rate-limiting — the scraper respects configured delays (`scraping.min_delay_seconds`/`max_delay_seconds`).
3. Some listings may have been removed from Rightmove (404 responses are logged and skipped).

### Enrichment errors (crime/supermarkets)

1. `data.police.uk` sometimes returns no data for rural locations — this is normal and expected. The property will still qualify if enrichment-dependent gates are not triggered.
2. Nominatim may return HTTP 429 (rate-limited) — the service sleeps 1.1 s between requests but heavy runs can still hit limits. Wait a few minutes and re-run `python -m src enrich`.
3. Run `python -m src enrich --limit 3` to test enrichment on a small batch.

### Report not opening

1. Run `python -m src report` manually — if it completes, open `output\reports\` in File Explorer and open the latest HTML file directly.
2. Check `output\reports\` exists and is not empty.
3. Run `python scripts/audit.py` to check for template rendering issues.

### Scheduler not running

1. Open Task Scheduler (search "Task Scheduler" in Start menu).
2. Find `PropertySearch_DailyRun` under "Task Scheduler Library".
3. Check "Last Run Time" and "Last Run Result" (0 = success).
4. Check the task is not disabled — right-click → Enable if needed.
5. Verify the PC was on and not sleeping at 7:00 AM (the task has "Start When Available" set, so it will catch up when the machine wakes up).

---

## Re-running Part of the Pipeline

### Just the report (no scraping)

```bash
python -m src report
```

### Just enrichment

```bash
python -m src enrich
```

### Just detail fetching

```bash
python -m src detail
```

### Search + report, skipping detail and enrichment

```bash
python -m src run --skip-detail
```

### One area only (full pipeline)

```bash
python -m src run --area "Paddock Wood"
```

### Regenerate report via the web UI

While `python -m src serve` is running, there is a "Regenerate" button in the report. Clicking it calls `POST /api/regenerate`, which re-runs the report generator in-process and refreshes the page — useful after favouriting/excluding properties.
