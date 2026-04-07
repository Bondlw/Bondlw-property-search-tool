"""Check Queripel gates and search for Springview at TN2 3SR."""
import sqlite3
import json
import yaml

conn = sqlite3.connect("data/property_search.db")
cur = conn.cursor()

with open("config/search_config.yaml") as f:
    config = yaml.safe_load(f)

from src.filtering.hard_gates import check_all_gates

# Check gates for all 3 Queripel properties
for pid in [1670, 1715, 1721]:
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
    print(f"#{pid}: {addr} | £{price:,} | {beds}bed")
    overall = "PASS" if passed else "FAIL"
    print(f"  Overall: {overall}")
    for g in gates:
        status = "PASS" if g.passed else "FAIL"
        verify = " [NEEDS VERIFY]" if g.needs_verification else ""
        print(f"  {status}{verify} {g.gate_name}: {g.reason}")
    print()

# Search for Springview / TN2 3SR
print("=" * 60)
print("Searching for Springview / Sandhurst Road / TN2 3SR...")
cur.execute(
    "SELECT id, address, price, status, bedrooms, property_type "
    "FROM properties WHERE address LIKE '%Springview%' OR address LIKE '%springview%' "
    "OR address LIKE '%TN2 3SR%' OR address LIKE '%Sandhurst Road%' OR address LIKE '%sandhurst%'"
)
rows = cur.fetchall()
print(f"Found {len(rows)} properties:")
for r in rows:
    print(f"  #{r[0]}: {r[1]} | £{r[2]:,} | status={r[3]} | {r[4]}bed | {r[5]}")

# Check GR config
print()
print("=" * 60)
print("GR Config:")
print(f"  ground_rent_max_pa: £{config.get('ground_rent_max_pa', '?')}")
tolerances = config.get("gate_tolerances", {})
print(f"  GR tolerance: £{tolerances.get('ground_rent_pa', '?')}/yr")

conn.close()
