"""
Scrape Rightmove listings for property sizes.
Strategy:
1. Extract from Rightmove's embedded PAGE_MODEL JSON (most reliable)
2. Extract from page body text (sq ft / sq m patterns)
3. Download floorplan images for manual review
"""
import sqlite3
import re
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


DB_PATH = "data/property_search.db"
FLOORPLAN_DIR = Path("data/floorplans")
FLOORPLAN_DIR.mkdir(parents=True, exist_ok=True)


def get_properties_without_size():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT portal_id, address, price 
        FROM properties 
        WHERE status = 'active' 
        AND (size_sqft IS NULL OR size_sqft = 0)
        AND price BETWEEN 140000 AND 210000
        AND (address LIKE '%Tunbridge Wells%' OR address LIKE '%Royal Tunbridge%')
        ORDER BY price
    """).fetchall()
    conn.close()
    return rows


def extract_size_from_text(text):
    """Try to find sq ft / sq m values in text."""
    sqft_patterns = [
        r'(\d[\d,]*)\s*(?:sq\.?\s*ft|sqft|square\s*feet)',
        r'(\d[\d,]*)\s*ft\s*²',
        r'(\d[\d,]*)\s*sq\s*ft',
    ]
    for pattern in sqft_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = int(match.group(1).replace(',', ''))
            if 100 < value < 3000:
                return value, 'sqft'

    sqm_patterns = [
        r'(\d[\d,]*\.?\d*)\s*(?:sq\.?\s*m|sqm|square\s*met|m²|m\s*²)',
    ]
    for pattern in sqm_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1).replace(',', ''))
            if 10 < value < 300:
                sqft = int(value * 10.764)
                return sqft, 'sqm_converted'

    return None, None


def extract_size_from_page_model(page):
    """Extract size from Rightmove's embedded PAGE_MODEL JavaScript object."""
    try:
        result = page.evaluate("""() => {
            // Rightmove embeds property data in window.PAGE_MODEL
            if (window.PAGE_MODEL && window.PAGE_MODEL.propertyData) {
                const pd = window.PAGE_MODEL.propertyData;
                return {
                    sizings: pd.sizings || null,
                    floorplans: pd.floorplans || null,
                    text: pd.text || null,
                    address: pd.address || null,
                };
            }
            return null;
        }""")

        if not result:
            return None, None, None

        # Check sizings array for sqft/sqm
        sizings = result.get("sizings")
        if sizings:
            for sizing in sizings:
                unit = sizing.get("unit", "")
                min_size = sizing.get("minimumSize", 0)
                max_size = sizing.get("maximumSize", 0)
                size_value = max_size or min_size
                if size_value:
                    if "sqft" in unit.lower() or "feet" in unit.lower():
                        return int(size_value), "page_model_sqft", result.get("floorplans")
                    elif "sqm" in unit.lower() or "metre" in unit.lower():
                        return int(float(size_value) * 10.764), "page_model_sqm", result.get("floorplans")

        return None, None, result.get("floorplans")

    except Exception:
        return None, None, None


def dismiss_cookie_banner(page):
    """Dismiss the OneTrust cookie consent overlay."""
    try:
        page.click("#onetrust-accept-btn-handler", timeout=3000)
        time.sleep(0.5)
    except Exception:
        # Try rejecting or closing via JS
        try:
            page.evaluate("""() => {
                const sdk = document.getElementById('onetrust-consent-sdk');
                if (sdk) sdk.remove();
                const overlay = document.querySelector('.onetrust-pc-dark-filter');
                if (overlay) overlay.remove();
            }""")
        except Exception:
            pass


def download_floorplan_image(page, floorplans_data, portal_id):
    """Download floorplan image using URL from PAGE_MODEL or page scraping."""
    floorplan_url = None

    # Try from PAGE_MODEL data first
    if floorplans_data:
        for floorplan in floorplans_data:
            url = floorplan.get("url") or floorplan.get("src")
            if url:
                if url.startswith("//"):
                    url = "https:" + url
                floorplan_url = url
                break

    # Fallback: scrape from page HTML
    if not floorplan_url:
        try:
            floorplan_url = page.evaluate("""() => {
                // Look for floorplan images in the page
                const imgs = document.querySelectorAll('img[src*="floorplan"], img[src*="floor"]');
                for (const img of imgs) {
                    if (img.src && img.src.includes('media.rightmove')) return img.src;
                }
                // Look for floorplan links
                const links = document.querySelectorAll('a[href*="floorplan"]');
                for (const a of links) {
                    const img = a.querySelector('img');
                    if (img && img.src) return img.src;
                }
                return null;
            }""")
        except Exception:
            pass

    if floorplan_url:
        screenshot_path = FLOORPLAN_DIR / f"{portal_id}.png"
        try:
            # Navigate to floorplan image directly and screenshot it
            floorplan_page = page.context.new_page()
            floorplan_page.goto(floorplan_url, timeout=10000)
            floorplan_page.screenshot(path=str(screenshot_path))
            floorplan_page.close()
            return str(screenshot_path), floorplan_url
        except Exception:
            pass

    return None, None


def scrape_sizes():
    properties = get_properties_without_size()
    print(f"Found {len(properties)} TW properties without sizes")
    print()

    results = {"found": [], "floorplan_saved": [], "no_data": [], "removed": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="msedge",
            headless=True,
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        cookie_dismissed = False

        for i, (portal_id, address, price) in enumerate(properties):
            print(f"[{i+1}/{len(properties)}] {portal_id} | {address} | £{price:,}")

            url = f"https://www.rightmove.co.uk/properties/{portal_id}"
            try:
                page.goto(url, timeout=15000, wait_until="domcontentloaded")
                time.sleep(1)

                # Dismiss cookie banner on first page load
                if not cookie_dismissed:
                    dismiss_cookie_banner(page)
                    cookie_dismissed = True

                # Check if listing still exists
                html_content = page.content()
                if "This property has been removed" in html_content or "Sorry, we can" in html_content:
                    print(f"  -> REMOVED from Rightmove")
                    results["removed"].append((portal_id, address, price))
                    continue

                # Strategy 1: Extract from PAGE_MODEL JavaScript object
                size_sqft, source, floorplans_data = extract_size_from_page_model(page)

                # Strategy 2: Extract from body text
                if not size_sqft:
                    body_text = page.inner_text("body")
                    size_sqft, source = extract_size_from_text(body_text)

                if size_sqft:
                    print(f"  -> FOUND: {size_sqft} sqft ({source})")
                    results["found"].append((portal_id, address, price, size_sqft, source))
                else:
                    # Strategy 3: Save floorplan image for manual review
                    screenshot_path, floorplan_url = download_floorplan_image(
                        page, floorplans_data, portal_id
                    )
                    if screenshot_path:
                        print(f"  -> Floorplan saved: {screenshot_path}")
                        results["floorplan_saved"].append(
                            (portal_id, address, price, screenshot_path)
                        )
                    else:
                        print(f"  -> No size or floorplan found")
                        results["no_data"].append((portal_id, address, price))

            except Exception as error:
                error_msg = str(error)[:100]
                print(f"  -> ERROR: {error_msg}")
                results["no_data"].append((portal_id, address, price))

            time.sleep(0.5)

        browser.close()

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print(f"\nSizes found: {len(results['found'])}")
    for portal_id, address, price, size, source in results["found"]:
        print(f"  {portal_id} | {address} | £{price:,} | {size} sqft ({source})")

    print(f"\nFloorplan images saved (need manual size read): {len(results['floorplan_saved'])}")
    for portal_id, address, price, path in results["floorplan_saved"]:
        print(f"  {portal_id} | {address} | £{price:,} | {path}")

    print(f"\nRemoved from Rightmove: {len(results['removed'])}")
    for portal_id, address, price in results["removed"]:
        print(f"  {portal_id} | {address} | £{price:,}")

    print(f"\nNo data at all: {len(results['no_data'])}")
    for portal_id, address, price in results["no_data"]:
        print(f"  {portal_id} | {address} | £{price:,}")

    # Auto-update DB for sizes found
    if results["found"]:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        for portal_id, address, price, size, source in results["found"]:
            cur.execute(
                "UPDATE properties SET size_sqft = ? WHERE portal_id = ?",
                (size, portal_id),
            )
        conn.commit()
        conn.close()
        print(f"\nDB updated with {len(results['found'])} sizes")

    # Auto-mark removed listings
    if results["removed"]:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        for portal_id, address, price in results["removed"]:
            cur.execute(
                "UPDATE properties SET status = 'removed' WHERE portal_id = ?",
                (portal_id,),
            )
        conn.commit()
        conn.close()
        print(f"DB updated: {len(results['removed'])} properties marked as removed")

    return results


if __name__ == "__main__":
    scrape_sizes()
