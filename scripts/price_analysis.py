import sqlite3

conn = sqlite3.connect('data/property_search.db')
conn.row_factory = sqlite3.Row

cursor = conn.execute('PRAGMA table_info(price_history)')
print('price_history columns:', [row['name'] for row in cursor.fetchall()])

rows = conn.execute('''
    SELECT ph.* FROM price_history ph
    JOIN properties p ON ph.property_id = p.id
    WHERE p.portal_id = 87629463
    ORDER BY ph.recorded_date
''').fetchall()
print(f'\nQueripel price history ({len(rows)} records):')
for r in rows:
    print(dict(r))

print('\n--- Comparable 1-bed flats in TN2 area ---')
rows2 = conn.execute('''
    SELECT address, price, size_sqft, tenure, status, first_listed_date, price_reduced
    FROM properties
    WHERE postcode LIKE 'TN2%'
    AND bedrooms = 1
    AND property_type = 'flat'
    ORDER BY price
''').fetchall()
for r in rows2:
    print(dict(r))

# Also check: how long has it been listed?
row = conn.execute('''
    SELECT first_listed_date, price, price_reduced
    FROM properties WHERE portal_id = 87629463
''').fetchone()
print(f'\n--- Queripel listing duration ---')
print(f'First listed: {row["first_listed_date"]}')
print(f'Current price: {row["price"]}')
print(f'Price reduced flag: {row["price_reduced"]}')

from datetime import date
listed = date.fromisoformat(row['first_listed_date'])
today = date(2026, 3, 26)
days_on_market = (today - listed).days
print(f'Days on market: {days_on_market}')

# Check all TN flats that have been reduced
print('\n--- Price-reduced flats in TN area ---')
rows3 = conn.execute('''
    SELECT address, price, size_sqft, first_listed_date, price_reduced
    FROM properties
    WHERE postcode LIKE 'TN%'
    AND property_type = 'flat'
    AND price_reduced = 1
    ORDER BY price
''').fetchall()
for r in rows3:
    print(dict(r))

conn.close()
