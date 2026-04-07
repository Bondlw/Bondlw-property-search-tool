#!/usr/bin/env python3
"""Check if Bramley Road is in the DB and look for room dimensions."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "property_search.db"
conn = sqlite3.connect(DB_PATH)

# Search for Bramley Road
rows = conn.execute(
    "SELECT address, size_sqft, rooms FROM properties WHERE address LIKE '%Bramley%'"
).fetchall()
print(f"Bramley results: {len(rows)}")
for r in rows:
    print(f"  Address: {r[0]}")
    print(f"  Size: {r[1]} sqft")
    print(f"  Rooms: {r[2][:500] if r[2] else 'None'}")
    print()

# Also check the current listing on Rightmove for this property
# portal_id from the URL: search by address
rows2 = conn.execute(
    "SELECT portal_id, address, size_sqft, rooms FROM properties WHERE address LIKE '%Snodland%' AND property_type NOT LIKE '%flat%'"
).fetchall()
print(f"\nSnodland non-flat results: {len(rows2)}")
for r in rows2:
    print(f"  Portal: {r[0]} | Address: {r[1]} | Size: {r[2]} sqft")
    if r[3]:
        print(f"  Rooms: {r[3][:300]}")
    print()

conn.close()
