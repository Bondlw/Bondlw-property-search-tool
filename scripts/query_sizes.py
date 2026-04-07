"""Query properties by size range with affordability tiers."""
import sqlite3

conn = sqlite3.connect('data/property_search.db')
cur = conn.cursor()

# Check for favourites table
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"Tables: {tables}")

# Check if there's a favourites table or column
has_favs_table = 'favourites' in tables

cur.execute("SELECT COUNT(*) FROM properties WHERE size_sqft IS NOT NULL AND size_sqft > 0 AND status = 'active'")
with_size = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM properties WHERE status = 'active'")
total_active = cur.fetchone()[0]

print(f"\n=== SIZE DATA COVERAGE ===")
print(f"Active properties: {total_active}")
print(f"With size data: {with_size} ({with_size*100//total_active}%)")
print(f"Without size data: {total_active - with_size}")

# Get favourite portal_ids if table exists
fav_ids = set()
if has_favs_table:
    cur.execute("SELECT p.portal_id FROM favourites f JOIN properties p ON f.property_id = p.id")
    fav_ids = {r[0] for r in cur.fetchall()}
    print(f"Favourites: {len(fav_ids)}")

print(f"\n=== PROPERTIES >= 460 sqft (Springview+ comfort zone) ===")
print(f"Sorted by size descending\n")

cur.execute("""
    SELECT portal_id, address, price, size_sqft, bedrooms, agent_name, price_reduced
    FROM properties 
    WHERE size_sqft >= 460 AND status = 'active'
    ORDER BY size_sqft DESC
""")
rows = cur.fetchall()

for row in rows:
    portal_id, address, price, size, beds, agent, reduced = row
    if price <= 160000:
        tier = "GREEN"
    elif price <= 175000:
        tier = "AMBER"
    elif price <= 200000:
        tier = "STRETCH"
    else:
        tier = "RED"
    fav_marker = " *" if str(portal_id) in fav_ids or portal_id in fav_ids else ""
    tag = ""
    if size >= 590:
        tag = " <<SWEET+>>"
    elif size >= 540:
        tag = " <MIN+>"
    elif size >= 483:
        tag = " ~SPRINGVIEW"
    elif size >= 460:
        tag = " (close)"
    beds_str = f"{beds}bed" if beds else ""
    reduced_str = " REDUCED" if reduced else ""
    print(f"  {tier:7s} {price:>7}  {size:>4} sqft  {beds_str:4s} {address}{fav_marker}{tag}{reduced_str}")

print(f"\nTotal: {len(rows)} properties >= 460 sqft")

print(f"\n=== PROPERTIES 400-459 sqft (below Springview) ===")
cur.execute("""
    SELECT portal_id, address, price, size_sqft, bedrooms, price_reduced
    FROM properties 
    WHERE size_sqft BETWEEN 400 AND 459 AND status = 'active'
    ORDER BY size_sqft DESC
""")
rows2 = cur.fetchall()
for row in rows2:
    portal_id, address, price, size, beds, reduced = row
    if price <= 160000:
        tier = "GREEN"
    elif price <= 175000:
        tier = "AMBER"
    elif price <= 200000:
        tier = "STRETCH"
    else:
        tier = "RED"
    fav_marker = " *" if str(portal_id) in fav_ids or portal_id in fav_ids else ""
    beds_str = f"{beds}bed" if beds else ""
    reduced_str = " REDUCED" if reduced else ""
    print(f"  {tier:7s} {price:>7}  {size:>4} sqft  {beds_str:4s} {address}{fav_marker}{reduced_str}")
print(f"Total: {len(rows2)} properties 400-459 sqft")

conn.close()
