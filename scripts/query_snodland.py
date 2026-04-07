"""Query Snodland properties."""
import sqlite3

conn = sqlite3.connect('data/property_search.db')
cur = conn.cursor()

cur.execute("""
    SELECT portal_id, address, price, property_type, tenure, bedrooms, size_sqft, 
           council_tax_band, service_charge_pa, ground_rent_pa, epc_rating,
           days_on_market, price_reduced, agent_name, title
    FROM properties 
    WHERE status = 'active' AND LOWER(address) LIKE '%snodland%'
    ORDER BY price ASC
""")
rows = cur.fetchall()

# Also check favourites
cur.execute("SELECT p.portal_id FROM favourites f JOIN properties p ON f.property_id = p.id")
fav_ids = {r[0] for r in cur.fetchall()}

for row in rows:
    pid, addr, price, ptype, tenure, beds, size, ctb, sc, gr, epc, dom, reduced, agent, title = row
    fav = " ★ FAV" if pid in fav_ids else ""
    tier = "GREEN" if price <= 160000 else "AMBER" if price <= 175000 else "STRETCH" if price <= 200000 else "RED"
    print(f"--- {pid} ---{fav}")
    print(f"  {tier} | {addr}")
    print(f"  £{price:,} | {ptype} | {tenure} | {beds or '?'}bed | {size or 'no size'} sqft")
    print(f"  CT Band: {ctb or '?'} | Service charge: £{sc or 0}/yr | Ground rent: £{gr or 0}/yr | EPC: {epc or '?'}")
    print(f"  Days on market: {dom or '?'} | Reduced: {'YES' if reduced else 'No'} | Agent: {agent or '?'}")
    print()

print(f"Total Snodland properties: {len(rows)}")

# Calculate monthly costs for freehold houses
print("\n=== MONTHLY COST BREAKDOWN (freehold houses) ===")
print("Assumes: £37,500 deposit, 4.5% rate, 30yr mortgage, £198/mo bills\n")

import math

deposit = 37500
rate_monthly = 0.045 / 12
term_months = 30 * 12
bills = 198

ct_bands = {"A": 91, "B": 109, "C": 127, "D": 145}

for row in rows:
    pid, addr, price, ptype, tenure, beds, size, ctb, sc, gr, epc, dom, reduced, agent, title = row
    
    mortgage_amount = price - deposit
    if mortgage_amount <= 0:
        continue
    
    monthly_mortgage = mortgage_amount * (rate_monthly * (1 + rate_monthly)**term_months) / ((1 + rate_monthly)**term_months - 1)
    ct_monthly = ct_bands.get(ctb, 127)  # default to C if unknown
    sc_monthly = (sc or 0) / 12
    gr_monthly = (gr or 0) / 12
    
    total_monthly = monthly_mortgage + bills + ct_monthly + sc_monthly + gr_monthly
    
    tier = "GREEN" if total_monthly <= 993 else "AMBER" if total_monthly <= 1072 else "STRETCH" if total_monthly <= 1200 else "RED"
    
    fav = " ★" if pid in fav_ids else ""
    print(f"  {addr}{fav}")
    print(f"    £{price:,} {ptype} ({tenure}) {beds or '?'}bed {size or '?'} sqft")
    print(f"    Mortgage: £{monthly_mortgage:.0f} + Bills: £{bills} + CT({ctb or 'C?'}): £{ct_monthly} + SC: £{sc_monthly:.0f} + GR: £{gr_monthly:.0f}")
    print(f"    TOTAL: £{total_monthly:.0f}/mo → {tier}")
    print()

conn.close()
