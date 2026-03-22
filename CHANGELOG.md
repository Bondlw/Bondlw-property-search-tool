# Changelog

All notable changes to the Property Search Tool are documented here.

## [0.1.0] — 2026-03-22

### Added
- **Config validation**: Full schema validation on `search_config.yaml` load with `ConfigValidationError`, type checking, range constraints, and cross-field validation.
- **Database backups**: Automated SQLite backup via `VACUUM INTO` before every report generation, with 5-file rotation.
- **CLI enhancements**: `--dry-run` and `--max-properties` flags on the `run` command.
- **API input validation**: 50KB max payload, JSON decode error handling, note length cap (5000 chars), CORS preflight support.
- **Template split**: Extracted CSS (`_styles.html`, 519 lines) and JS (`_scripts.html`, 1593 lines) from `daily_report.html` via Jinja2 `{% include %}`.
- **Floorplan vision**: Claude Haiku-powered floor plan size extraction from images (`floorplan_vision.py`).
- **Viewing inspections**: Post-viewing condition scoring (light, noise, parking, storage, pros/cons).
- **Offers tracking**: Track offers with amount, date, status, and notes.
- **Viewings scheduling**: Book and manage property viewings with date, time, and status.
- **Negotiation analysis**: Discount signals based on days on market, lease years, and price history.
- **Stretch opportunities**: Identify properties slightly over budget that could qualify at a negotiated price.
- **Deposit recommendations**: Auto-calculate optimal deposit to keep monthly costs within GREEN/AMBER ceilings.
- **Area statistics**: Per-area aggregates (avg price, crime, days listed) in report.
- **Supermarket backfill**: Batch enrichment of nearest supermarket distances via Nominatim OSM.
- **Station backfill**: Batch enrichment of nearest station walk times.
- **Favourites import**: Playwright-based import of Rightmove saved properties.

### Changed
- **Error handling**: Replaced bare `except Exception:` with specific exception types across `repository.py`, `report_server.py`, and `cli.py`. All `logger.error` calls now include `exc_info=True`.
- **Database transactions**: Added `conn.rollback()` on failure in `insert_property` and `update_property`.
- **Schema migrations**: Database schema upgraded to v5 (viewings, offers, viewing_inspections tables).

### Fixed
- N+1 query pattern in property enrichment lookups.
- Floor/cap conflict in financial calculator when lease premium pushed monthly over green ceiling.

### Testing
- 199 tests passing across 8 test files.
- Coverage on critical modules: config_loader, repository, server, scoring, hard_gates, financial_calculator, geo.
