"""Quick check: how many properties match the similar-to-Queripel criteria."""
import sys
sys.path.insert(0, ".")

from src.storage.database import Database
from src.storage.repository import PropertyRepository

database = Database("data/property_search.db")
repo = PropertyRepository(database)
props = repo.get_active_properties()

ref_size = 542
ref_price = 179950
size_min = ref_size * 0.85
size_max = ref_size * 1.15
price_min = ref_price * 0.85
price_max = ref_price * 1.15

with_size = [p for p in props if p.get("size_sqft")]
matches = [
    p for p in with_size
    if size_min <= p["size_sqft"] <= size_max
    and price_min <= p["price"] <= price_max
    and str(p.get("portal_id")) != "87629463"
]

print(f"Active properties: {len(props)}")
print(f"With size data: {len(with_size)}")
print(f"Similar to Queripel (±15% size & price): {len(matches)}")
print(f"\nSize range: {size_min:.0f} – {size_max:.0f} sqft")
print(f"Price range: £{price_min:,.0f} – £{price_max:,.0f}")

if matches:
    print(f"\nMatches:")
    for m in matches:
        addr = (m.get("address") or m.get("title") or "-")[:55]
        size_diff = abs(m["size_sqft"] - ref_size) / ref_size * 100
        price_diff = abs(m["price"] - ref_price) / ref_price * 100
        similarity = round(100 - (size_diff + price_diff) / 2, 1)
        ppsf = round(m["price"] / m["size_sqft"]) if m["size_sqft"] else 0
        print(f"  {addr:55s}  £{m['price']:>7,}  {m['size_sqft']:>4} sqft  £{ppsf}/sqft  {similarity}% match")
else:
    print("\nNo matches found.")
