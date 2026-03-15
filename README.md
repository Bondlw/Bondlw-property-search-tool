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
