#!/usr/bin/env python3
"""
Import Rightmove saved properties as favourites in the local database.

Usage:
    python scripts/import_rightmove_favourites.py

Requirements:
    pip install playwright
    playwright install chromium  (first time only)

How it works:
    1. Opens a Chromium browser window pointed at your Rightmove saved properties.
    2. Waits for you to log in (if needed).
    3. Scrapes all saved property IDs across all pages.
    4. Matches them against your local database by portal_id.
    5. Adds matches to the favourites table.
"""

import re
import sys
import sqlite3
import time
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
DB_PATH   = REPO_ROOT / "data" / "property_search.db"

# ── Rightmove URL ─────────────────────────────────────────────────────────────
SAVED_URL = "https://www.rightmove.co.uk/user/saved-properties"

# ── Regex to extract property IDs from page source / links ───────────────────
PROP_ID_RE = re.compile(r"rightmove\.co\.uk/properties/(\d+)")


def _extract_ids_from_page(page) -> list[str]:
    """Extract all Rightmove property IDs from the current page via JS evaluation."""
    # Method 1: query all <a> hrefs containing /properties/
    ids_from_links: list[str] = page.evaluate("""
        () => {
            const hrefs = Array.from(document.querySelectorAll('a[href*="/properties/"]'))
                .map(a => a.href);
            const ids = hrefs.map(h => { const m = h.match(/\\/properties\\/(\\d+)/); return m ? m[1] : null; })
                .filter(Boolean);
            return [...new Set(ids)];
        }
    """)

    # Method 2: fallback — scan full page HTML for /properties/NNNNN patterns
    if not ids_from_links:
        html = page.content()
        ids_from_links = list(dict.fromkeys(PROP_ID_RE.findall(html)))

    return ids_from_links


def scrape_saved_ids() -> list[str]:
    """Launch Edge via Playwright and collect all saved property IDs.
    
    Saves cookies/storage state so login is remembered for future runs.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("ERROR: playwright not installed.")
        print("  Run:  pip install playwright && playwright install chromium")
        sys.exit(1)

    all_ids: list[str] = []
    storage_path = str(REPO_ROOT / ".playwright-state.json")

    with sync_playwright() as pw:
        print("\n  Launching Edge...")

        browser = pw.chromium.launch(
            channel="msedge",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )

        # Load saved cookies/storage if available from a previous run
        if Path(storage_path).exists():
            print("  Loading saved login session...")
            context = browser.new_context(storage_state=storage_path)
        else:
            context = browser.new_context()

        page = context.new_page()
        page.goto(SAVED_URL, wait_until="domcontentloaded", timeout=30_000)

        # If redirected to login, wait for the user to complete it
        if "/login" in page.url.split("?")[0] or "/account" in page.url.split("?")[0]:
            print("  ⏳ Please log in to Rightmove in the browser window.")
            print("     Google SSO and all login methods should work.")
            print("     Waiting up to 5 minutes...\n")
            try:
                # Match the path after the domain — excludes ?from= query params
                page.wait_for_url(
                    re.compile(r"\.co\.uk/user/saved-properties"),
                    timeout=300_000,
                )
            except PWTimeout:
                print("  ERROR: Timed out waiting for login (5 minutes).")
                browser.close()
                sys.exit(1)
            time.sleep(2)

        print(f"  ✓ On saved-properties page: {page.url[:80]}")

        # Scrape all pages
        page_num = 0
        while True:
            page_num += 1

            try:
                page.wait_for_selector(
                    'a[href*="/properties/"], [data-test*="property"], .propertyCard, .l-searchResult',
                    timeout=15_000,
                )
            except PWTimeout:
                pass

            time.sleep(1.5)
            found = _extract_ids_from_page(page)
            new_ids = [pid for pid in found if pid not in all_ids]
            all_ids.extend(new_ids)
            print(f"  Page {page_num}: found {len(new_ids)} property IDs (running total: {len(all_ids)})")

            if not new_ids and page_num > 1:
                print("  No new IDs on this page — stopping.")
                break

            next_btn = page.query_selector(
                'a[data-test="pagination-next"], button[aria-label="Next page"], '
                'a[aria-label="Next"], .pagination-list a:last-child'
            )
            if next_btn and next_btn.is_visible():
                next_btn.click()
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except PWTimeout:
                    pass
            else:
                break

        # Save cookies/storage for next run so login persists
        context.storage_state(path=storage_path)
        print("  ✓ Login session saved for future runs.")
        browser.close()

    return list(dict.fromkeys(all_ids))  # deduplicate preserving order


def import_to_db(rightmove_ids: list[str]) -> tuple[int, int, list[str]]:
    """Match portal_ids against DB and add to favourites. Returns (added, already_fav, not_found)."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    added          = 0
    already_fav    = 0
    not_found_ids: list[str] = []

    for rm_id in rightmove_ids:
        cur.execute("SELECT id FROM properties WHERE portal_id = ?", (rm_id,))
        row = cur.fetchone()
        if not row:
            not_found_ids.append(rm_id)
            continue

        prop_db_id = row[0]
        cur.execute("SELECT 1 FROM favourites WHERE property_id = ?", (prop_db_id,))
        if cur.fetchone():
            already_fav += 1
        else:
            cur.execute(
                "INSERT OR IGNORE INTO favourites (property_id, notes) VALUES (?, ?)",
                (prop_db_id, "Imported from Rightmove saved properties"),
            )
            added += 1

    conn.commit()
    conn.close()
    return added, already_fav, not_found_ids


def main():
    print("=" * 60)
    print("  Rightmove Saved Properties → Local Favourites Importer")
    print("=" * 60)

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    print("\nStep 1: Scraping Rightmove saved properties…")
    rm_ids = scrape_saved_ids()
    print(f"\n  Total unique property IDs found: {len(rm_ids)}")

    if not rm_ids:
        print("No property IDs found. Exiting.")
        sys.exit(0)

    print("\nStep 2: Importing into local database…")
    added, already_fav, not_found = import_to_db(rm_ids)

    print(f"\n  ✓ Added to favourites:     {added}")
    print(f"  ✓ Already favourited:      {already_fav}")
    print(f"  ✗ Not in local DB:         {len(not_found)}")
    if not_found:
        print(f"\n  Rightmove IDs not in DB (probably outside your search areas):")
        for pid in not_found:
            print(f"    https://www.rightmove.co.uk/properties/{pid}")

    if added > 0:
        print(f"\n  Regenerating report to include new favourites…")
        try:
            sys.path.insert(0, str(REPO_ROOT))
            from src.config_loader import load_config
            from src.reporting.report_generator import ReportGenerator
            from src.storage.database import Database
            from src.storage.repository import PropertyRepository
            from datetime import date

            config = load_config()
            output_path = str(REPO_ROOT / "output" / "reports" / f"report_{date.today().isoformat()}.html")
            with Database(str(DB_PATH)) as db:
                repo = PropertyRepository(db)
                properties      = repo.get_active_properties()
                enrichment_map  = {p["id"]: e for p in properties if (e := repo.get_enrichment(p["id"]))}
                ph_map          = {p["id"]: h for p in properties if (h := repo.get_price_history(p["id"]))}
                fav_ids         = repo.get_favourite_ids()
                excl_ids        = repo.get_excluded_ids()

            ReportGenerator(config).generate(
                properties, output_path, enrichment_map,
                favourite_ids=fav_ids, excluded_ids=excl_ids,
                price_history_map=ph_map,
            )
            print(f"  ✓ Report regenerated: {output_path}")
            import webbrowser
            webbrowser.open(f"file:///{Path(output_path).resolve()}")
        except Exception as exc:
            print(f"  Report regeneration failed: {exc}")
            print("  Run 'python -m src report' manually.")

    print("\nDone.")


if __name__ == "__main__":
    main()
