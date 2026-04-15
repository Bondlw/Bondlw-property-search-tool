# Property Search Tool — Agent Context

## Project Purpose

Rightmove property listing scraper and aggregator. Searches for properties matching configurable criteria, scrapes listing details, and produces structured reports. Uses a `PAGE_MODEL` pattern for resilient scraping against Rightmove's dynamic page structure.

## Stack

- Python 3.x
- Playwright (browser automation for Rightmove scraping)
- `PAGE_MODEL` abstraction for page structure resilience
- Output: JSON listings, Markdown reports, optional HTML dashboard

## MCP Servers Available

### Playwright MCP
The primary tool for resilient browser-based scraping.

**Use for:**
- Navigating Rightmove search result pages
- Extracting listing data (price, location, bedrooms, agent, URL)
- Handling Rightmove's cookie consent dialogs and dynamic page loading
- Taking screenshots of listings for visual review
- Debugging PAGE_MODEL selectors when Rightmove updates its structure

**Do not use Playwright MCP for production data collection** — use the scripted `PAGE_MODEL` pipeline for batch runs. Use Playwright MCP for:
1. Testing new PAGE_MODEL selectors
2. Debugging extraction failures
3. One-off interactive searches

## PAGE_MODEL Pattern

The scraper uses a `PAGE_MODEL` dict to define selectors for each data field. When selectors break (Rightmove updates its HTML), update `PAGE_MODEL` rather than individual scraping functions.

```python
PAGE_MODEL = {
    "price": ".propertyCard-priceValue",
    "address": ".propertyCard-address",
    "bedrooms": ".property-information span[data-testid='beds']",
    # ...
}
```

## Development Patterns

- Selector testing: use Playwright MCP to navigate live Rightmove and verify selectors interactively
- Rate limiting: always include delays between requests — Rightmove blocks aggressive scrapers
- No login required: public listings only — no credentials needed
- Output immutability: write new results to new files, never overwrite existing data

## Key Files

- `README.md` — Setup, usage, and PAGE_MODEL reference
- Main scraper script in project root
