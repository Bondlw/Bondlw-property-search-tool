"""Add standout picks to favourites."""
from src.storage.database import Database
from src.storage.repository import PropertyRepository

db = Database()
repo = PropertyRepository(db)

new_favs = [1724, 1710, 1639]
for pid in new_favs:
    repo.add_favourite(pid, "")
    row = db.conn.execute("SELECT address FROM properties WHERE id=?", (pid,)).fetchone()
    print(f"Added #{pid} {row[0]}")

print()
favs = repo.get_favourites()
print(f"Total favourites: {len(favs)}")
for fav in favs:
    pid = fav["property_id"]
    row = db.conn.execute("SELECT address FROM properties WHERE id=?", (pid,)).fetchone()
    addr = row[0] if row else "?"
    print(f"  #{pid} {addr}")
