# Property Search Tool — Architecture & Technical Reference

## Overview

Automated UK property search tool that scrapes Rightmove, applies hard-gate filtering, scores qualifying properties on a 100-point scale, and generates a self-contained HTML daily report with financial analysis, enrichment data, and interactive favouriting/exclusion.

**Search focus:** Tunbridge Wells cluster — 5 areas (Tunbridge Wells, Southborough, Paddock Wood, Marden, Staplehurst) on the Southeastern mainline, all with direct services to London.

**Tech stack:** Python 3.13, SQLite, Click CLI, Jinja2 HTML reports, Requests + BeautifulSoup scraping, Windows Task Scheduler for daily automation.

---

## Directory Structure

```
Property Search Tool/
├── config/
│   ├── search_config.yaml      # Single source of truth — all criteria, areas, financials
│   └── user_agent_pool.txt     # Rotating user-agents for HTTP requests
├── data/
│   └── property_search.db      # SQLite database (gitignored)
├── docs/
│   ├── ARCHITECTURE.md         # This file — technical reference
│   ├── WORKFLOW.md             # Pipeline steps, CLI commands, scheduler setup
│   └── USER_GUIDE.md           # Non-technical guide for reading and using the tool
├── output/
│   └── reports/                # Generated HTML reports (gitignored)
├── scripts/
│   ├── audit.py                # Report health-check: validates HTML output for issues
│   ├── diagnostic.py           # Prints qualifying/near-miss breakdown to console
│   ├── fix_tenure.py           # Re-scrape and correct tenure for freehold+SC anomalies
│   ├── gate_analysis.py        # Show which gates are filtering out properties
│   ├── import_rightmove_favourites.py  # Playwright-based import of Rightmove saved properties
│   ├── scenario_analysis.py    # Deposit/term scenario financial modelling
│   ├── setup_scheduler.ps1     # Windows Task Scheduler setup for daily runs
│   └── verify_counts.py        # Quick qualifying vs needs-verification count check
├── src/
│   ├── __main__.py             # Entry point: python -m src <command>
│   ├── cli.py                  # Click CLI command definitions
│   ├── config_loader.py        # YAML config loading
│   ├── enrichment/
│   │   ├── enrichment_service.py   # Crime data, supermarket proximity, commute lookup
│   │   └── floorplan_vision.py     # Claude Haiku vision — extract floor area from plan images
│   ├── filtering/
│   │   ├── hard_gates.py           # 15+ hard-gate checks (price, lease, EPC, crime, etc.)
│   │   └── scoring.py              # Multi-factor weighted scoring engine (0–100 points)
│   ├── notifications/
│   │   └── notifier.py             # Windows toast + email notifications
│   ├── reporting/
│   │   └── report_generator.py     # Builds Jinja2 context and renders daily_report.html
│   ├── scrapers/
│   │   ├── base_scraper.py         # Abstract scraper base class
│   │   ├── http_client.py          # Requests session with rotating UA, retry, rate-limit
│   │   └── rightmove_scraper.py    # Rightmove search + listing detail parser
│   ├── server/
│   │   └── report_server.py        # Local HTTP server for interactive report (API endpoints)
│   ├── storage/
│   │   ├── database.py             # SQLite connection manager and schema init/migrations
│   │   ├── models.py               # Dataclasses: RawListing, Property, EnrichmentData, etc.
│   │   └── repository.py           # All CRUD, enrichment, price history, favourites, notes
│   └── utils/
│       ├── deduplication.py        # URL normalisation to prevent duplicate inserts
│       ├── financial_calculator.py # Mortgage, monthly cost, affordability rating
│       └── geo.py                  # Haversine distance calculations (miles and metres)
└── templates/
    ├── daily_report.html       # Jinja2 HTML report template (dark theme)
    ├── _styles.html            # Extracted CSS partial (~519 lines)
    └── _scripts.html           # Extracted JS partial (~1593 lines)
```

---

## System Components

### Scrapers (`src/scrapers/`)

**`http_client.py`** — manages a `requests.Session` with a rotating user-agent pool drawn from `config/user_agent_pool.txt`. Handles retries, rate-limiting (configurable min/max delay in `search_config.yaml`), and timeout handling.

**`rightmove_scraper.py`** — two-phase scraper:

1. **Search phase** — hits the Rightmove search endpoint for each configured area/Rightmove ID. Parses the JSON `PAGE_MODEL` embedded in the page HTML to extract listing summaries (price, address, postcode, property type, portal ID).
2. **Detail phase** — fetches each individual listing page and extracts full details: tenure, lease years, service charge, ground rent, council tax band, EPC rating, description, key features, floorplan URLs, images, room dimensions, nearest stations, agent name, and coordinates.

### Storage (`src/storage/`)

**`database.py`** — manages the SQLite connection. Runs `init_schema()` on entry, which creates all tables idempotently and applies any pending schema migrations (currently at version 4). Uses WAL journal mode and enforces foreign keys.

**`models.py`** — dataclasses used across the system:

- `RawListing` — data extracted from a portal before DB storage
- `Property` — full property record retrieved from DB
- `EnrichmentData` — external API data attached to a property
- `PropertyScore` — scoring breakdown (6 weighted components)
- `GateResult` — result of a single hard gate check
- `Exclusion` — a user-excluded property

**`repository.py`** — all database operations. Key responsibilities:

- `insert_property` / `update_property` — insert new or update existing listings; always records an initial price history entry
- `update_property_details` — selective update; only overwrites non-null detail fields, preserving existing data
- `upsert_enrichment` — dynamic INSERT or UPDATE for enrichment data
- Favourites, exclusions, notes, tracking status, viewings — full CRUD for each
- `log_run` — writes a run summary to `run_log`
- `get_properties_needing_details` — active properties missing description or images
- `get_properties_needing_enrichment` — active properties with coordinates but no crime data

### Enrichment (`src/enrichment/enrichment_service.py`)

Fetches three categories of data per property:

1. **Crime data** — queries `data.police.uk/api/crimes-at-location` using the property's lat/lng. Tries the last 3 months in reverse order, uses the first successful response. Normalises raw crime categories to: `asb`, `burglary`, `drugs`, `violent`, `vehicle`, `total`.

2. **Supermarkets** — uses the Nominatim OpenStreetMap API to find the nearest location for each of: Lidl, Aldi, Tesco, Sainsbury's, Asda, Morrisons, Co-op, Waitrose, M&S Food. Stores the best (nearest any chain) as `nearest_supermarket_*`, and also stores Lidl/Aldi individually for backwards compatibility. Respects Nominatim's 1 req/s rate limit.

3. **Commute times** — a pure config lookup (no API). Matches by nearest station name or postcode district prefix to the `commute_lookup` table in `search_config.yaml`. Returns `commute_to_london_min`, `commute_to_maidstone_min`, `annual_season_ticket`.

Station data (name, distance, walk minutes) is extracted from the Rightmove listing page during the detail fetch and stored at that time — not during the enrichment step.

### Filtering (`src/filtering/`)

**`hard_gates.py`** — 15 gates that all must pass for a property to qualify. Gates are run in order; all results are collected (not short-circuited) so the report can show exactly which gates failed.

**`scoring.py`** — 100-point scoring engine applied only to qualifying properties (all gates passed). Six weighted components:

| Component             | Default weight | What it measures                                                   |
| --------------------- | -------------- | ------------------------------------------------------------------ |
| Financial Fit         | 30 pts         | All-in monthly cost vs GREEN/AMBER/RED targets                     |
| Crime Safety          | 25 pts         | Per-category crime counts vs good thresholds                       |
| Cost Predictability   | 15 pts         | Tenure, lease length, service charge, ground rent stability        |
| Layout Livability     | 15 pts         | Bedroom count, EPC, outdoor space, parking, separate lounge        |
| Walkability           | 10 pts         | Walk minutes to station and nearest supermarket                    |
| Long-term Flexibility | 5 pts          | Tenure type, property type, London commute time, chain-free status |

### Reporting (`src/reporting/report_generator.py`)

Applies all gates and scoring to every active property, then sorts them into sections:

- **Qualifying** — passed all gates; GREEN monthly cost. Sorted: new today first, then by total score descending.
- **Favourites** — user-starred properties; shown in a dedicated section regardless of gate status.
- **Opportunities** — two sub-types merged into one section:
  - _Negotiation targets_: only price/affordability gates fail, and a negotiated offer would bring them into budget; on market 30+ days.
  - _Stretch_: between monthly target and 40% of take-home; 60+ days on market; negotiated offer would qualify.
- **Near Misses** — failed gates but not in Opportunities. Sorted by gate severity (minor failures first), deduplicated against Opportunities.
- **New Today** — first seen today across all sections.

Each property card also shows: recommended offer price (based on days on market + price reduction history), deposit recommendation (minimum deposit to reach GREEN), financial cost breakdown, enrichment data, and a negotiation analysis.

Area statistics (total listings, qualifying count, average price, average crime, average days listed) are computed per configured search area and shown in a summary table.

### Server (`src/server/report_server.py`)

A `SimpleHTTPRequestHandler` subclass that serves the latest report at `/` and exposes REST API endpoints:

| Method | Endpoint                | Action                                                                 |
| ------ | ----------------------- | ---------------------------------------------------------------------- |
| POST   | `/api/favourite/<id>`   | Toggle favourite (add if not favourited, remove if already favourited) |
| POST   | `/api/unfavourite/<id>` | Remove from favourites                                                 |
| POST   | `/api/exclude/<id>`     | Exclude property with a reason                                         |
| POST   | `/api/unexclude/<id>`   | Remove exclusion                                                       |
| POST   | `/api/note/<id>`        | Save/update a note                                                     |
| GET    | `/api/note/<id>`        | Retrieve note text                                                     |
| POST   | `/api/tracking/<id>`    | Set tracking status                                                    |
| GET    | `/api/statuses`         | Bulk fetch all favourites + exclusions                                 |
| POST   | `/api/regenerate`       | Re-generate today's report in-process                                  |
| POST   | `/api/viewing`          | Add a viewing                                                          |
| POST   | `/api/enquiry/<id>`     | Launch Playwright to auto-fill Rightmove contact form                  |

All changes persist to the SQLite database. The `/api/regenerate` endpoint re-renders the report so favouriting/excluding a property in the browser is immediately reflected on next page load.

### Notifications (`src/notifications/notifier.py`)

On completion of a full pipeline run, sends:

- **Windows toast notification** — via `winotify` (preferred) or PowerShell `Windows.UI.Notifications` fallback. Shows qualifying count, new today count, near-miss count.
- **Email** — HTML email via SMTP (Gmail or configurable). Disabled by default; requires `smtp_password` to be configured in `notifications` section of config. Includes a top-5 qualifying properties table.

---

## Data Flow

```
config/search_config.yaml
       │  (areas, budget, hard gate thresholds, commute lookup)
       ▼
RightmoveScraper.search()
       │  → RawListing objects (price, address, postcode, type, portal_id)
       ▼
PropertyRepository.insert_property() / update_property()
       │  → properties + price_history tables
       ▼
RightmoveScraper.get_listing_detail()
       │  → tenure, lease, SC, GR, EPC, description, images, stations, coords
       ▼
PropertyRepository.update_property_details() + upsert_enrichment() (stations)
       │
       ▼
EnrichmentService.enrich()
       │  → crime (police.uk), supermarkets (Nominatim OSM), commute (config lookup)
       ▼
PropertyRepository.upsert_enrichment()
       │
       ▼
ReportGenerator.generate()
       │  → check_all_gates() per property → pass / [failed gates]
       │  → score_property() for qualifying properties
       │  → FinancialCalculator: monthly cost, offer recommendation, deposit recommendation
       │  → sort into qualifying / opportunities / near_misses / favourites
       ▼
output/reports/report_YYYY-MM-DD.html
       │
       ▼
Notifier.notify()  →  Windows toast + email
webbrowser.open()  →  auto-open in default browser
```

---

## Database Schema

The database lives at `data/property_search.db` (current schema version: 5).

### `properties`

Core table. One row per unique listing (deduplicated by `portal` + `portal_id`).

Key columns: `id`, `portal`, `portal_id`, `url`, `url_normalised`, `price`, `address`, `postcode`, `property_type`, `bedrooms`, `bathrooms`, `tenure`, `lease_years`, `service_charge_pa`, `ground_rent_pa`, `council_tax_band`, `epc_rating`, `description`, `key_features` (JSON), `images` (JSON), `floorplan_urls` (JSON), `rooms` (JSON), `latitude`, `longitude`, `first_seen_date`, `last_seen_date`, `first_listed_date`, `is_active`, `status`, `price_reduced`.

### `price_history`

One row per price change. References `properties(id)`. Stores `price`, `recorded_date`, `change_amount`, `change_pct`. An initial entry is created when a property is first inserted.

### `enrichment_data`

One row per property (unique on `property_id`). Contains: nearest station (name, distance, walk minutes), nearest supermarket (name, distance, walk minutes), individual Lidl/Aldi distances for backwards compatibility, crime summary (JSON), crime safety score, commute times to London and Maidstone, annual season ticket cost, flood zone, broadband speed, verified council tax band.

### `favourites`

Set of property IDs the user has starred. Contains `property_id`, `notes`, `added_at`.

### `exclusions`

Properties permanently hidden from report sections. Contains `property_id`, `reason`, `excluded_by`, `excluded_at`.

### `property_notes`

One note per property (upsert). Free-text field editable from the web UI.

### `property_tracking`

Tracks a property's pipeline status. Valid statuses: `new`, `reviewing`, `contacted`, `viewing_booked`, `viewed`, `offer_made`, `rejected`, `archived`.

### `viewings`

Scheduled and completed viewings. Contains `property_id`, `viewing_date`, `viewing_time`, `status`, `notes`.

### `gate_results` / `scores`

Stored gate check results and scoring breakdowns (written by the report generator; used for display).

### `run_log`

One row per pipeline run. Records `run_type`, `properties_found`, `new_properties`, `updated_properties`, `qualifying_count`, `duration_seconds`, `errors` (JSON array).

### `search_areas`

Mirror of the search areas defined in config. Populated on first run.

---

## Hard Gates Reference

All 15 gates in `hard_gates.py` must pass for a property to qualify. Gates marked with an asterisk are only evaluated when enrichment data exists.

| Gate                     | Threshold (default)                            | Notes                                                                           |
| ------------------------ | ---------------------------------------------- | ------------------------------------------------------------------------------- |
| `price_cap`              | Freehold ≤£190k, Leasehold ≤£180k              | Tenure-specific; checks monthly cost if between responsible and absolute max    |
| `monthly_cost`           | Housing ≤£795/mo (GREEN)                       | Definitive affordability gate — AMBER (£795–928) properties go to Opportunities |
| `min_bedrooms`           | ≥1 bedroom                                     | Rejects studios/bedsits                                                         |
| `separate_lounge`        | Not studio or bedsit                           | Checks property type and description text                                       |
| `move_in_ready`          | No renovation/cash-only terms                  | Rejects modernisation projects and cash-buyers-only listings                    |
| `not_retirement`         | No retirement/sheltered terms                  | Rejects over-55 and assisted living                                             |
| `not_auction`            | No auction indicators                          | "Guide price" alone is not a trigger                                            |
| `not_non_standard`       | No houseboat/caravan/park home                 | Checks type, title, and first 300 chars of description                          |
| `lease_length`           | Standard ≥120yr, SOF ≥80yr                     | Freehold passes unconditionally                                                 |
| `service_charge`         | ≤£1,200/yr                                     | Leasehold/SOF only                                                              |
| `ground_rent`            | ≤£250/yr                                       | Leasehold/SOF only                                                              |
| `no_doubling_clause`     | No doubling/escalating GR terms                | Leasehold/SOF only; checks description                                          |
| `no_tbc_fields`          | No TBC near SC/GR/lease/CT                     | Rejects if "TBC" appears within 50 chars of a key financial field               |
| `council_tax_band`       | ≤Band C                                        | Pass if unknown (too rarely published by Rightmove)                             |
| `epc_rating`             | ≥C                                             | Pass if unknown (same reason)                                                   |
| `station_walkable`\*     | ≤25 min walk                                   | Only runs when enrichment data exists                                           |
| `supermarket_walkable`\* | ≤30 min walk                                   | Prefers any major chain; falls back to Lidl/Aldi                                |
| `crime_safety`\*         | Violent ≤8, ASB ≤10, Burglary ≤3, Drugs ≤3 /mo | Per-category thresholds from config                                             |
| `flood_risk`\*           | Zone < 3                                       | Zone 3 rejected; Zone 2 flagged                                                 |

---

## Configuration Reference (`config/search_config.yaml`)

| Section                  | Key field                  | Current value                               | Meaning                                                              |
| ------------------------ | -------------------------- | ------------------------------------------- | -------------------------------------------------------------------- |
| `user`                   | `deposit`                  | £37,500                                     | Available deposit for all mortgage calculations                      |
| `user`                   | `mortgage_rate`            | 4.5%                                        | Annual rate used across all scenarios                                |
| `user`                   | `mortgage_term_years`      | 30                                          | Repayment term                                                       |
| `user`                   | `monthly_take_home`        | £2,650                                      | Used for affordability percentage calculations                       |
| `monthly_target`         | `min`                      | £795                                        | GREEN ceiling — housing ≤30% of take-home                            |
| `monthly_target`         | `max`                      | £928                                        | AMBER ceiling — housing ≤35% of take-home                            |
| `estimated_bills`        | `total_monthly`            | £211                                        | Energy + water + insurance + broadband + TV licence                  |
| `budget.freehold`        | `absolute_max`             | £190,000                                    | Hard price cap for freehold properties                               |
| `budget.leasehold`       | `absolute_max`             | £180,000                                    | Hard price cap for leasehold properties                              |
| `hard_gates`             | `lease_minimum_years`      | 120                                         | Minimum remaining lease for standard leasehold                       |
| `hard_gates`             | `sof_lease_minimum_years`  | 80                                          | Minimum remaining lease for share of freehold                        |
| `hard_gates`             | `service_charge_max_pa`    | £1,200                                      | Annual service charge cap                                            |
| `hard_gates`             | `ground_rent_max_pa`       | £250                                        | Annual ground rent cap                                               |
| `hard_gates`             | `council_tax_max_band`     | C                                           | Maximum council tax band                                             |
| `hard_gates`             | `epc_minimum_rating`       | C                                           | Minimum EPC energy rating                                            |
| `hard_gates`             | `station_max_walk_min`     | 25                                          | Max walk to nearest station (minutes)                                |
| `hard_gates`             | `supermarket_max_walk_min` | 30                                          | Max walk to nearest supermarket (minutes)                            |
| `hard_gates`             | `flood_zone_reject`        | 3                                           | Reject properties in Flood Zone 3+                                   |
| `max_radius_miles`       | —                          | 10                                          | Skip DB properties further than this from any configured area centre |
| `excluded_address_terms` | —                          | maidstone, sevenoaks, tonbridge, monchelsea | Address substrings that exclude a property from all report sections  |
| `scoring`                | all weights                | 30/25/15/15/10/5                            | Weights for the 6 scoring components (sum to 100)                    |

### Search Areas

Five areas in the primary cluster (all Southeastern mainline):

| Area            | Rightmove ID | Train to London         |
| --------------- | ------------ | ----------------------- |
| Tunbridge Wells | REGION^1366  | ~56 min (Charing Cross) |
| Southborough    | REGION^22779 | ~52 min (High Brooms)   |
| Paddock Wood    | REGION^19244 | ~46 min (Charing Cross) |
| Marden          | REGION^16723 | ~67 min (Charing Cross) |
| Staplehurst     | REGION^23175 | ~63 min (Charing Cross) |

---

## Scripts Reference

| Script                                   | Purpose                                                                      |
| ---------------------------------------- | ---------------------------------------------------------------------------- |
| `scripts/audit.py`                       | Parse latest HTML report and flag any template/data issues                   |
| `scripts/diagnostic.py`                  | Print qualifying/near-miss breakdown to console without regenerating         |
| `scripts/import_rightmove_favourites.py` | Use Playwright to import Rightmove saved properties as local favourites      |
| `scripts/fix_tenure.py`                  | Re-scrape freehold properties with service charges to correct tenure         |
| `scripts/gate_analysis.py`               | Show which hard gates are filtering out the most properties                  |
| `scripts/scenario_analysis.py`           | Deposit and mortgage term scenario analysis                                  |
| `scripts/setup_scheduler.ps1`            | Register daily run as Windows Task Scheduler job (`PropertySearch_DailyRun`) |
| `scripts/verify_counts.py`              | Quick qualifying vs needs-verification count check                           |

---

## Key Invariants

- Properties are deduplicated by `(portal, portal_id)`. URL normalisation is a secondary dedup check.
- `update_property` only touches `price`, `last_seen_date`, `is_active`, `status`, `price_reduced`. It never overwrites detail fields that were populated by a detail fetch.
- `update_property_details` only overwrites fields that are non-null in the incoming `RawListing`.
- Enrichment data is upserted (not replaced wholesale) — existing fields survive partial updates.
- Hard gates are re-evaluated fresh on every report generation from the current DB data. Gate results are not cached across runs.
- Properties in the `exclusions` table are completely hidden from qualifying, near-miss, and opportunities sections, but are still shown in a dedicated excluded section on the report.
- A property only enters Opportunities if: (a) the only failing gates are `price_cap` and/or `monthly_cost`, AND (b) a calculated negotiated offer would bring the monthly cost within the GREEN target.
