"""Quick diagnostic: check qualifying properties and their areas."""
from src.config_loader import load_config
from src.storage.database import Database
from src.storage.repository import PropertyRepository
from src.reporting.report_generator import ReportGenerator

config = load_config()
db = Database()
repo = PropertyRepository(db)

props = repo.get_active_properties()
enrichment_map = {}
for p in props:
    e = repo.get_enrichment(p["id"])
    if e:
        enrichment_map[p["id"]] = e

fav_ids = set(repo.get_favourite_ids())
excl_ids = set(repo.get_excluded_ids())
price_history_map = {}
for p in props:
    ph = repo.get_price_history(p["id"])
    if ph:
        price_history_map[p["id"]] = ph

rg = ReportGenerator(config)
path = rg.generate(props, "output/reports/test_check.html", enrichment_map, fav_ids, excl_ids, price_history_map)

print(f"Input properties: {len(props)}")
print(f"Favourites: {len(fav_ids)}")
print(f"Excluded: {len(excl_ids)}")
print(f"Qualifying: {len(rg.last_qualifying)}")
print(f"Near misses: {len(rg.last_near_misses)}")
print()

print("--- Qualifying ---")
for p in rg.last_qualifying:
    area = p.get("_search_area", "?")
    addr = p.get("address", p.get("title", "?"))
    price = p.get("price", 0)
    print(f"  #{p['id']} {addr} | {area} | £{price:,}")

print()
print("--- Favourites ---")
# Check favourited property areas
for p in props:
    if p["id"] in fav_ids:
        lat, lng = p.get("latitude"), p.get("longitude")
        if lat and lng:
            name, dist = rg._nearest_area(lat, lng)
            print(f"  #{p['id']} {p.get('address','?')} | {name} ({dist:.1f}mi)")
        else:
            print(f"  #{p['id']} {p.get('address','?')} | no coords")
