"""Find freehold houses in budget range."""
import sqlite3

conn = sqlite3.connect('data/property_search.db')
cur = conn.cursor()

# Check property_type values
print("=== PROPERTY TYPES ===")
cur.execute("SELECT DISTINCT property_type, COUNT(*) FROM properties WHERE status = 'active' GROUP BY property_type ORDER BY COUNT(*) DESC")
for row in cur.fetchall():
    print(f"  {row}")

print("\n=== TENURE VALUES ===")
cur.execute("SELECT DISTINCT tenure, COUNT(*) FROM properties WHERE status = 'active' GROUP BY tenure ORDER BY COUNT(*) DESC")
for row in cur.fetchall():
    print(f"  {row}")

# Now find freehold houses
print("\n=== FREEHOLD HOUSES (any price, active) ===")
cur.execute("""
    SELECT portal_id, address, price, property_type, tenure, bedrooms, size_sqft, title
    FROM properties 
    WHERE status = 'active'
      AND LOWER(tenure) LIKE '%freehold%'
      AND LOWER(property_type) NOT LIKE '%flat%'
      AND LOWER(property_type) NOT LIKE '%apartment%'
    ORDER BY price ASC
""")
rows = cur.fetchall()
for row in rows:
    portal_id, address, price, ptype, tenure, beds, size, title = row
    if price <= 160000:
        tier = "GREEN"
    elif price <= 175000:
        tier = "AMBER"
    elif price <= 200000:
        tier = "STRETCH"
    else:
        tier = "RED"
    size_str = f"{size} sqft" if size else "no size"
    beds_str = f"{beds}bed" if beds else ""
    print(f"  {tier:7s} {price:>7}  {beds_str:4s} {size_str:>10s}  {ptype or '?':20s}  {address}")

print(f"\nTotal freehold non-flat: {len(rows)}")

# Also check for houses that might be leasehold but are houses
print("\n=== ALL HOUSES (any tenure, STRETCH or better) ===")
cur.execute("""
    SELECT portal_id, address, price, property_type, tenure, bedrooms, size_sqft
    FROM properties 
    WHERE status = 'active'
      AND price <= 200000
      AND (LOWER(property_type) LIKE '%house%' 
           OR LOWER(property_type) LIKE '%terrace%'
           OR LOWER(property_type) LIKE '%cottage%'
           OR LOWER(property_type) LIKE '%bungalow%'
           OR LOWER(property_type) LIKE '%maisonette%'
           OR LOWER(property_type) LIKE '%end of terrace%')
    ORDER BY price ASC
""")
rows2 = cur.fetchall()
for row in rows2:
    portal_id, address, price, ptype, tenure, beds, size = row
    if price <= 160000:
        tier = "GREEN"
    elif price <= 175000:
        tier = "AMBER"
    elif price <= 200000:
        tier = "STRETCH"
    else:
        tier = "RED"
    size_str = f"{size} sqft" if size else "no size"
    beds_str = f"{beds}bed" if beds else ""
    tenure_str = tenure or "unknown"
    print(f"  {tier:7s} {price:>7}  {beds_str:4s} {size_str:>10s}  {tenure_str:12s}  {ptype or '?':20s}  {address}")

print(f"\nTotal houses <= 200k: {len(rows2)}")

# Also check titles for 'house' keyword in case property_type is null/generic
print("\n=== FREEHOLD PROPERTIES (all types, STRETCH or better) ===")
cur.execute("""
    SELECT portal_id, address, price, property_type, tenure, bedrooms, size_sqft, title
    FROM properties 
    WHERE status = 'active'
      AND price <= 200000
      AND LOWER(tenure) LIKE '%freehold%'
    ORDER BY price ASC
""")
rows3 = cur.fetchall()
for row in rows3:
    portal_id, address, price, ptype, tenure, beds, size, title = row
    if price <= 160000:
        tier = "GREEN"
    elif price <= 175000:
        tier = "AMBER"
    elif price <= 200000:
        tier = "STRETCH"
    else:
        tier = "RED"
    size_str = f"{size} sqft" if size else "no size"
    beds_str = f"{beds}bed" if beds else ""
    print(f"  {tier:7s} {price:>7}  {beds_str:4s} {size_str:>10s}  {ptype or '?':20s}  {address}")

print(f"\nTotal freehold <= 200k: {len(rows3)}")

conn.close()
