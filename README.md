# Property Search Tool

Automated UK property search tool for the Tunbridge Wells cluster. Scrapes Rightmove daily, applies financial and quality hard gates, scores candidates, and generates a self-contained HTML report.

## Quick Start

```bash
# Install
pip install -e .

# Initialise database
python -m src init

# Run full pipeline (scrape → enrich → report)
python -m src run

# Dry-run: see what would be scraped without saving
python -m src run --dry-run

# Limit to 5 properties per area
python -m src run --max-properties 5

# Generate report from existing data (no scraping)
python -m src report

# Browse reports in browser at http://localhost:8080
python -m src serve
```

Reports are saved to `output/reports/report_YYYY-MM-DD.html`.

## Search Areas

Tunbridge Wells cluster — all on Southeastern mainline (~50 min to London Bridge):

- Tunbridge Wells
- Southborough
- Paddock Wood
- Marden
- Staplehurst

## What the Report Shows

| Section | Description |
|---------|-------------|
| **Qualifying** | Pass all gates, GREEN monthly cost (≤£795/mo housing) |
| **Opportunities** | Would qualify at an achievable offer; includes negotiation targets and stretch properties |
| **Near Misses** | Close-call failures, sorted by how resolvable the gate failure is |
| **New Today** | Properties added in today's scrape |

## Key Criteria

- Deposit: £37,500
- Mortgage: 4.5%, 30-year term
- Monthly housing cap: £795 GREEN / £928 AMBER
- Freehold price range: ideal £170k–£180k, absolute max £190k
- Leasehold price range: ideal £150k–£165k, absolute max £180k
- Lease minimum: 120 years standard, 80 years for share of freehold
- EPC: C or better
- Council tax: Band C or lower
- Station walk: ≤25 minutes
- Excluded areas: Maidstone, Sevenoaks, Tonbridge, Monchelsea

Full configuration in `config/search_config.yaml`. Technical architecture in `docs/ARCHITECTURE.md`.

## Project Structure

```
config/         Search criteria and user-agent pool
data/           SQLite database (gitignored)
docs/           Architecture reference and criteria docs
output/         Generated reports, logs, exports (gitignored)
scripts/        Utility scripts (audit, diagnostic, import, scheduler)
src/            Application source code
templates/      Jinja2 HTML report template
tests/          Test suite
```

## Requirements

Python 3.10+. Dependencies in `requirements.txt` / `pyproject.toml`.

## CLI Commands

| Command | Description | Key Flags |
|---------|-------------|-----------|
| `init` | Create database schema | — |
| `run` | Full pipeline: search → detail → enrich → report | `--dry-run`, `--max-properties N`, `--skip-detail`, `--area NAME` |
| `search` | Scrape listings only | `--portal`, `--area` |
| `detail` | Fetch full listing details | `--limit N` |
| `enrich` | Crime, walkability, commute enrichment | `--limit N` |
| `report` | Generate HTML report from DB | — |
| `serve` | Local HTTP server for reports + API | `--port N` |
| `backfill-supermarkets` | Find nearest Lidl/Aldi for all properties | — |
| `backfill-stations` | Update nearest station data | — |
| `floorplan-size` | Extract sizes from floorplan images | — |

## API Endpoints

The report server (`python -m src serve`) exposes REST endpoints for interactive features:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/favourite/<id>` | Add to favourites |
| POST | `/api/unfavourite/<id>` | Remove from favourites |
| POST | `/api/exclude/<id>` | Exclude property (body: `{"reason": "..."}`) |
| POST | `/api/unexclude/<id>` | Remove exclusion |
| POST | `/api/note/<id>` | Save note (body: `{"text": "..."}`, max 5000 chars) |
| GET | `/api/note/<id>` | Get note for property |
| GET | `/api/notes` | All notes |
| POST | `/api/tracking/<id>` | Set tracking status (body: `{"status": "..."}`) |
| GET | `/api/trackings` | All tracking statuses |
| POST | `/api/viewing` | Add viewing (body: `{property_id, viewing_date, ...}`) |
| GET | `/api/viewings` | All viewings |
| POST | `/api/offer` | Record offer (body: `{property_id, amount, ...}`) |
| GET | `/api/offers` | All offers |
| POST | `/api/inspection` | Save post-viewing inspection |
| GET | `/api/inspection/<viewing_id>` | Get inspection for viewing |
| POST | `/api/regenerate` | Re-run report generation |

**Input limits:** 50KB max payload, JSON validation on all POST endpoints, CORS enabled.

## Config Validation

The config file (`config/search_config.yaml`) is validated on load:

- **Required sections:** `user`, `budget`, `monthly_target`, `hard_gates`, `scoring`
- **Type checking:** All keys validated against expected types
- **Range validation:** Numeric fields checked against sensible bounds (warnings, not errors)
- **Cross-field validation:** `monthly_target.min < max`, scoring weights sum to 100

Invalid configs raise `ConfigValidationError` with clear diagnostic messages.

## Database Backups

Automatic SQLite backups are created before every report generation:
- Stored in `data/backups/`
- Timestamped filenames: `property_search_YYYYMMDD_HHMMSS.db`
- Retains the 5 most recent backups (older ones auto-deleted)

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=term-missing
```
