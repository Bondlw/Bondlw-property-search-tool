"""Fix tenure for freehold properties that have service charges (likely share_of_freehold)."""
import sqlite3
from src.scrapers.http_client import HttpClient
from src.scrapers.rightmove_scraper import RightmoveScraper
from src.config_loader import load_config

config = load_config()
conn = sqlite3.connect("data/property_search.db")
conn.row_factory = sqlite3.Row

suspect = conn.execute(
    """SELECT id, url, address, tenure, service_charge_pa
    FROM properties
    WHERE is_active = 1 AND tenure = 'freehold' AND service_charge_pa > 0"""
).fetchall()

print(f"Freehold with SC > 0: {len(suspect)}")

http_client = HttpClient(config)
scraper = RightmoveScraper(http_client)

for prop in [dict(s) for s in suspect]:
    try:
        listing = scraper.get_listing_detail(prop["url"])
        if listing and listing.tenure and listing.tenure != prop["tenure"]:
            conn.execute(
                "UPDATE properties SET tenure = ?, updated_at = datetime('now') WHERE id = ?",
                (listing.tenure, prop["id"]),
            )
            conn.commit()
            print(f"  Fixed: {prop['address']} -> {listing.tenure}")
        else:
            t = listing.tenure if listing else "no listing"
            print(f"  No change: {prop['address']} (scraper: {t})")
    except Exception as e:
        print(f"  Error: {prop['address']}: {e}")

for t in ["freehold", "leasehold", "share_of_freehold"]:
    c = conn.execute(
        "SELECT COUNT(*) FROM properties WHERE is_active = 1 AND tenure = ?", (t,)
    ).fetchone()
    print(f"{t}: {c[0]}")

conn.close()
