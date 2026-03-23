"""Check which favourites survive radius/exclusion filtering."""
import sys
sys.path.insert(0, ".")

from src.storage.database import Database
from src.storage.repository import PropertyRepository
from src.config_loader import load_config
from src.reporting.report_generator import ReportGenerator

config = load_config()
db = Database()
repo = PropertyRepository(db)
gen = ReportGenerator(config)

fav_ids = repo.get_favourite_ids()
excl_ids = repo.get_excluded_ids()
properties = repo.get_active_properties()
max_radius = config.get("max_radius_miles", 10)
excluded_locations = config.get("excluded_address_terms", [])

print(f"Total active: {len(properties)}")
print(f"Favourite IDs: {sorted(fav_ids)}")
print(f"Excluded IDs: {sorted(excl_ids)}")
print(f"Max radius: {max_radius} miles")
print(f"Excluded terms: {excluded_locations}")
print()

visible_count = 0
for prop in properties:
    if prop["id"] not in fav_ids:
        continue

    lat = prop.get("latitude")
    lng = prop.get("longitude")
    pid = prop["id"]
    addr = prop.get("address", "?")[:50]

    if lat and lng:
        area_name, area_dist = gen._nearest_area(lat, lng)
        in_radius = area_dist <= max_radius
    else:
        area_name = "Unknown"
        area_dist = None
        in_radius = True

    addr_lower = (prop.get("address") or prop.get("title") or "").lower()
    location_excluded = any(term.lower() in addr_lower for term in excluded_locations)

    user_excluded = pid in excl_ids

    status = "✓ VISIBLE"
    if not in_radius:
        status = f"✗ RADIUS-FILTERED ({area_dist:.1f}mi > {max_radius}mi)"
    elif location_excluded:
        status = "✗ LOCATION-EXCLUDED"
    elif user_excluded:
        status = "✗ USER-EXCLUDED"
    else:
        visible_count += 1

    dist_str = f"{area_dist:.1f}mi" if area_dist is not None else "no coords"
    print(f"  #{pid} {addr} — area={area_name} dist={dist_str} — {status}")

print(f"\nVisible favourites: {visible_count} / {len(fav_ids)}")
