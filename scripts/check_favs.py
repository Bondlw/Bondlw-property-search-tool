"""Quick script to check Queripel and list favourites with URLs."""
from src.storage.database import Database

db = Database()
conn = db.conn

# Check for Queripel
rows = conn.execute(
    "SELECT id, address, title, price, status, last_seen_date, url FROM properties "
    "WHERE address LIKE '%queripel%' OR title LIKE '%queripel%'"
).fetchall()
print("=== Queripel in DB ===")
if not rows:
    print("  Not found")
for r in rows:
    d = dict(r)
    print(f"  id={d['id']}  £{d['price']}  {d['address']}  status={d['status']}  last_seen={d['last_seen_date']}")
    print(f"    URL: {d.get('url', 'N/A')}")

# Check if Queripel was ever in favourites table (including deleted)
print("\n=== Queripel IDs in favourites table ===")
q_ids = [dict(r)["id"] for r in rows]
for qid in q_ids:
    fav_row = conn.execute("SELECT * FROM favourites WHERE property_id = ?", (qid,)).fetchone()
    print(f"  prop {qid}: {'YES - favourited' if fav_row else 'NOT in favourites'}")

# All favourites with URLs
print("\n=== Current Favourites ===")
favs = conn.execute(
    "SELECT p.id, p.address, p.title, p.price, p.status, p.last_seen_date, p.url "
    "FROM properties p JOIN favourites f ON f.property_id = p.id ORDER BY p.price"
).fetchall()
for f in favs:
    d = dict(f)
    addr = (d.get("address") or d.get("title") or "")[:55]
    print(f"  {d['id']:>5}  £{d.get('price','?'):>8}  {addr:<55}  {d.get('status','?'):<10}  {d.get('url','')}")

print(f"\nTotal favourites: {len(favs)}")
conn.close()
