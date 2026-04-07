"""Check Springview gates and look at how GR is displayed in report."""
import sqlite3
import json
import yaml

conn = sqlite3.connect("data/property_search.db")
cur = conn.cursor()

with open("config/search_config.yaml") as f:
    config = yaml.safe_load(f)

from src.filtering.hard_gates import check_all_gates

# Check Springview #1682 gates
for pid in [1682, 1641]:
    cur.execute("SELECT * FROM properties WHERE id = ?", (pid,))
    prop_row = cur.fetchone()
    prop_cols = [d[0] for d in cur.description]
    prop = dict(zip(prop_cols, prop_row))

    cur.execute("SELECT * FROM enrichment_data WHERE property_id = ?", (pid,))
    enr_row = cur.fetchone()
    enr = None
    if enr_row:
        enr_cols = [d[0] for d in cur.description]
        enr = dict(zip(enr_cols, enr_row))

    passed, gates = check_all_gates(prop, enr, config)
    price = prop.get("price", 0)
    beds = prop.get("bedrooms", "?")
    addr = prop.get("address", "?")
    sc = prop.get("service_charge_pa", "?")
    gr = prop.get("ground_rent_pa", "?")
    lease = prop.get("lease_years", "?")
    url = prop.get("url", "?")
    print(f"#{pid}: {addr}")
    print(f"  Price: £{price:,} | {beds}bed | SC: £{sc}/yr | GR: £{gr}/yr | Lease: {lease}yr")
    print(f"  URL: {url}")
    overall = "PASS" if passed else "FAIL"
    print(f"  Overall: {overall}")
    for g in gates:
        status = "PASS" if g.passed else "FAIL"
        verify = " [NEEDS VERIFY]" if g.needs_verification else ""
        print(f"  {status}{verify} {g.gate_name}: {g.reason}")
    print()

# Show GR config details
print("=" * 60)
print("GR-related config:")
print(f"  ground_rent_max_pa: {config.get('ground_rent_max_pa', 'NOT SET')}")
tolerances = config.get("gate_tolerances", {})
print(f"  GR tolerance: {tolerances.get('ground_rent_pa', 'NOT SET')}/yr")

# Check what "expensive_ground_rent" means in the report
# Search for red_flags logic
print()
print("=" * 60)
print("Checking red_flags field in properties table...")
cur.execute("SELECT id, address, red_flags FROM properties WHERE address LIKE '%Queripel%' OR address LIKE '%Springview%' OR address LIKE '%Sandhurst%'")
for row in cur.fetchall():
    print(f"  #{row[0]}: {row[1]} -> red_flags: {row[2]}")

conn.close()
