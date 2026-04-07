import sqlite3
import json

conn = sqlite3.connect('data/property_search.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

ids = ['87629463', '171409649', '163721603']
for pid in ids:
    cur.execute(
        "SELECT id, address, price, url, status, property_type, tenure, "
        "lease_years, service_charge_pa, ground_rent_pa, bedrooms, size_sqft, "
        "council_tax_band, is_active, portal_id "
        "FROM properties WHERE url LIKE ? OR portal_id = ?",
        (f'%{pid}%', pid)
    )
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f'\n=== Property {pid} ===')
            for k in r.keys():
                val = r[k]
                if k == 'url' and val:
                    val = val[:80]
                print(f'  {k}: {val}')
    else:
        print(f'\n=== Property {pid} === NOT FOUND IN DATABASE')

conn.close()
