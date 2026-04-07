"""Find all Queripel Close properties in the database."""
import sqlite3

conn = sqlite3.connect("data/property_search.db")
cur = conn.cursor()

# All Queripel properties
cur.execute(
    "SELECT id, address, price, status, bedrooms, property_type "
    "FROM properties WHERE address LIKE '%Queripel%' OR address LIKE '%queripel%'"
)
rows = cur.fetchall()
print(f"All Queripel properties ({len(rows)}):")
for row in rows:
    print(f"  #{row[0]}: {row[1]} | price={row[2]} | status={row[3]} | beds={row[4]} | type={row[5]}")

# Excluded?
cur.execute(
    "SELECT e.property_id, e.reason, p.address FROM exclusions e "
    "JOIN properties p ON e.property_id = p.id WHERE p.address LIKE '%Queripel%'"
)
excl = cur.fetchall()
print(f"\nExcluded Queripel ({len(excl)}):")
for exclusion in excl:
    print(f"  #{exclusion[0]}: {exclusion[2]} - reason: {exclusion[1]}")

# Favourited?
cur.execute(
    "SELECT f.property_id, p.address FROM favourites f "
    "JOIN properties p ON f.property_id = p.id WHERE p.address LIKE '%Queripel%'"
)
favs = cur.fetchall()
print(f"\nFavourited Queripel ({len(favs)}):")
for fav in favs:
    print(f"  #{fav[0]}: {fav[1]}")

# Also search for "32" in address to catch variations
cur.execute(
    "SELECT id, address, price, status FROM properties "
    "WHERE address LIKE '%32%' AND (address LIKE '%Queripel%' OR address LIKE '%Close%')"
)
addr32 = cur.fetchall()
print(f"\nProperties with '32' near 'Queripel/Close' ({len(addr32)}):")
for prop in addr32:
    print(f"  #{prop[0]}: {prop[1]} | price={prop[2]} | status={prop[3]}")

# Check enrichment data for existing Queripel properties
for row in rows:
    cur.execute("SELECT * FROM enrichment_data WHERE property_id = ?", (row[0],))
    enrichment = cur.fetchone()
    has_enrichment = "YES" if enrichment else "NO"
    print(f"\n  #{row[0]} enrichment: {has_enrichment}")
    if enrichment:
        cols = [desc[0] for desc in cur.description]
        for col_name, value in zip(cols, enrichment):
            if value is not None and col_name != "property_id":
                print(f"    {col_name}: {value}")

conn.close()
