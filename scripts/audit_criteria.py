"""Investigate Springview Apartments and run full criteria audit."""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.database import Database
from src.filtering.hard_gates import check_all_gates
from src.config_loader import load_config

config = load_config()
db = Database()
conn = db.conn

# --- Part 1: Find Springview ---
print("=" * 60)
print("SPRINGVIEW INVESTIGATION")
print("=" * 60)
rows = conn.execute(
    "SELECT p.* FROM properties p "
    "WHERE p.address LIKE '%springview%' OR p.title LIKE '%springview%' "
    "OR p.address LIKE '%spring view%' ORDER BY p.id"
).fetchall()
print(f"Found {len(rows)} Springview properties\n")
for r in rows:
    d = dict(r)
    pid = d["id"]
    print(f"  #{pid} | {d.get('address', 'N/A')} | {d.get('title', 'N/A')}")
    print(f"    Price: {d.get('price')} | Status: {d.get('status')} | Tenure: {d.get('tenure')}")
    print(f"    SC: {d.get('service_charge_pa')} | GR: {d.get('ground_rent_pa')} | Lease: {d.get('lease_years')}")
    print(f"    EPC: {d.get('epc_rating')} | CT Band: {d.get('council_tax_band')} | Beds: {d.get('bedrooms')}")
    print(f"    Last seen: {d.get('last_seen_date')}")

    exc = conn.execute("SELECT reason FROM exclusions WHERE property_id = ?", (pid,)).fetchone()
    if exc:
        print(f"    ** EXCLUDED: {exc[0]}")

    fav = conn.execute("SELECT 1 FROM favourites WHERE property_id = ?", (pid,)).fetchone()
    if fav:
        print(f"    ** IS A FAVOURITE")

    # Run gates
    enr = conn.execute("SELECT * FROM enrichment_data WHERE property_id = ?", (pid,)).fetchone()
    enrichment = dict(enr) if enr else {}
    passed, gates = check_all_gates(d, enrichment, config)
    failed_gates = [g for g in gates if not g.passed]
    flagged_gates = [g for g in gates if g.passed and g.needs_verification]
    print(f"    Gates: overall={'PASS' if passed else 'FAIL'}")
    for g in failed_gates:
        print(f"      FAIL: {g.gate_name} — {g.reason}")
    for g in flagged_gates:
        print(f"      FLAG: {g.gate_name} — {g.reason}")
    print()

# Also search for "9" + "spring" patterns
print("\nSearching for '9' + 'spring' combinations...")
rows2 = conn.execute(
    "SELECT id, address, title, price, status FROM properties "
    "WHERE (address LIKE '%9%spring%' OR title LIKE '%9%spring%' "
    "OR address LIKE '%spring%9%' OR title LIKE '%spring%9%') ORDER BY id"
).fetchall()
for r in rows2:
    d = dict(r)
    print(f"  #{d['id']} | {d['address']} | {d['title']} | £{d['price']} | {d['status']}")

# Search broadly on Sandhurst Road (where Springview is)
print("\nAll Sandhurst Road properties:")
rows3 = conn.execute(
    "SELECT id, address, title, price, status, last_seen_date FROM properties "
    "WHERE address LIKE '%sandhurst%' ORDER BY id"
).fetchall()
for r in rows3:
    d = dict(r)
    print(f"  #{d['id']} | {d['address'][:60]} | £{d['price']} | {d['status']} | {d['last_seen_date']}")

# Non-active Springview
print("\nNon-active Springview:")
rows4 = conn.execute(
    "SELECT id, address, title, price, status, last_seen_date FROM properties "
    "WHERE status != 'active' AND (address LIKE '%springview%' OR title LIKE '%springview%') ORDER BY id"
).fetchall()
if rows4:
    for r in rows4:
        d = dict(r)
        print(f"  #{d['id']} | {d['address'][:60]} | {d['status']} | {d['last_seen_date']}")
else:
    print("  None found.")

# --- Part 2: Full Criteria Audit ---
print("\n" + "=" * 60)
print("FULL CRITERIA AUDIT")
print("=" * 60)

# Get all active properties
active = conn.execute("SELECT p.* FROM properties p WHERE p.status = 'active'").fetchall()
print(f"Total active properties: {len(active)}\n")

qualifying = []
needs_verification = []
near_misses = []  # fail by 1 gate only
hard_fails = []

for row in active:
    prop = dict(row)
    pid = prop["id"]
    enr = conn.execute("SELECT * FROM enrichment_data WHERE property_id = ?", (pid,)).fetchone()
    enrichment = dict(enr) if enr else {}
    passed, gates = check_all_gates(prop, enrichment, config)
    failed_gates = [g for g in gates if not g.passed]
    flagged_gates = [g for g in gates if g.passed and g.needs_verification]

    is_fav = conn.execute("SELECT 1 FROM favourites WHERE property_id = ?", (pid,)).fetchone()
    is_excluded = conn.execute("SELECT reason FROM exclusions WHERE property_id = ?", (pid,)).fetchone()

    record = {
        "id": pid,
        "address": prop.get("address", ""),
        "price": prop.get("price"),
        "passed": passed,
        "failed_gates": [(g.gate_name, g.reason) for g in failed_gates],
        "flagged_gates": [(g.gate_name, g.reason) for g in flagged_gates],
        "is_favourite": bool(is_fav),
        "is_excluded": is_excluded[0] if is_excluded else None,
    }

    if passed and not flagged_gates:
        qualifying.append(record)
    elif passed and flagged_gates:
        needs_verification.append(record)
    elif len(failed_gates) <= 2:
        near_misses.append(record)
    else:
        hard_fails.append(record)

print(f"Qualifying (all gates pass, no flags): {len(qualifying)}")
print(f"Needs verification (pass with flags): {len(needs_verification)}")
print(f"Near misses (1-2 gate failures): {len(near_misses)}")
print(f"Hard fails (3+ gate failures): {len(hard_fails)}")

# Check for problems: qualifying/needs-verification that are excluded
print("\n--- PROBLEM: Qualifying properties that are EXCLUDED ---")
problems_found = False
for r in qualifying + needs_verification:
    if r["is_excluded"]:
        problems_found = True
        print(f"  #{r['id']} {r['address']} — EXCLUDED ({r['is_excluded']}) but passes all gates!")
if not problems_found:
    print("  None found.")

# Check for problems: favourites that are failing
print("\n--- PROBLEM: Favourites that FAIL gates ---")
problems_found = False
for r in near_misses + hard_fails:
    if r["is_favourite"]:
        problems_found = True
        fails = ", ".join(f"{name}: {reason}" for name, reason in r["failed_gates"])
        print(f"  #{r['id']} {r['address']} — FAVOURITE but fails: {fails}")
if not problems_found:
    print("  None found.")

# Show all favourites and their status
print("\n--- ALL FAVOURITES STATUS ---")
favs = conn.execute("SELECT property_id FROM favourites").fetchall()
for f in favs:
    pid = f[0]
    prop_row = conn.execute("SELECT * FROM properties WHERE id = ?", (pid,)).fetchone()
    if not prop_row:
        print(f"  #{pid} — NOT IN DATABASE (orphaned favourite)")
        continue
    prop = dict(prop_row)
    enr = conn.execute("SELECT * FROM enrichment_data WHERE property_id = ?", (pid,)).fetchone()
    enrichment = dict(enr) if enr else {}
    passed, gates = check_all_gates(prop, enrichment, config)
    failed_gates = [g for g in gates if not g.passed]
    flagged_gates = [g for g in gates if g.passed and g.needs_verification]
    exc = conn.execute("SELECT reason FROM exclusions WHERE property_id = ?", (pid,)).fetchone()

    status_emoji = "✓" if passed else "✗"
    fav_status = f"  {status_emoji} #{pid} {prop.get('address', 'N/A')} | £{prop.get('price')} | status={prop.get('status')}"
    if exc:
        fav_status += f" | EXCLUDED: {exc[0]}"
    if failed_gates:
        fails = ", ".join(f"{g.gate_name}" for g in failed_gates)
        fav_status += f" | FAILS: {fails}"
    if flagged_gates:
        flags = ", ".join(f"{g.gate_name}" for g in flagged_gates)
        fav_status += f" | FLAGS: {flags}"
    print(fav_status)
