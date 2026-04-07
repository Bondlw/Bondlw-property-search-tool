"""Check active properties for SSTC status on Rightmove."""
import sqlite3
import json
import time
import requests

conn = sqlite3.connect("data/property_search.db")
cursor = conn.cursor()
cursor.execute("SELECT portal_id, address FROM properties WHERE is_active = 1 ORDER BY RANDOM() LIMIT 15")
props = cursor.fetchall()

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
sold_ids = []

for portal_id, addr in props:
    url = f"https://www.rightmove.co.uk/properties/{portal_id}"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 410:
            print(f"GONE: {portal_id} - {addr[:50]}")
            sold_ids.append(portal_id)
            continue
        html = resp.text
        marker = "window.PAGE_MODEL = "
        idx = html.find(marker)
        if idx > -1:
            js = idx + len(marker)
            depth, i = 0, js
            while i < len(html):
                if html[i] == "{":
                    depth += 1
                elif html[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            data = json.loads(html[js : i + 1])
            pd = data.get("propertyData", {})
            tags = pd.get("tags", [])
            if tags:
                print(f"{tags}: {portal_id} - {addr[:50]}")
                if any(t.upper() in ("SOLD_STC", "UNDER_OFFER") for t in tags):
                    sold_ids.append(portal_id)
            else:
                print(f"OK: {portal_id} - {addr[:50]}")
        time.sleep(0.5)
    except Exception as exc:
        print(f"ERR: {portal_id} - {exc}")

print(f"\nChecked {len(props)}, sold/gone: {len(sold_ids)}")
if sold_ids:
    print(f"IDs to deactivate: {sold_ids}")
conn.close()
