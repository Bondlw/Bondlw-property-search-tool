#!/usr/bin/env python3
"""Analyse all favourites and rank them by best option."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "property_search.db"
conn = sqlite3.connect(DB_PATH)

rows = conn.execute('''
    SELECT p.portal_id, p.address, p.price, p.size_sqft, p.tenure, p.lease_years,
           p.service_charge_pa, p.ground_rent_pa, p.council_tax_band,
           p.is_active, p.property_type, p.bedrooms, p.bathrooms,
           p.days_on_market, p.epc_rating, p.postcode,
           s.financial_fit, s.crime_safety, s.cost_predictability,
           s.layout_livability, s.walkability, s.long_term_flexibility, s.total_score,
           e.nearest_station_name, e.nearest_station_walk_min, e.commute_to_london_min,
           e.crime_safety_score, e.nearest_supermarket_walk_min,
           p.status
    FROM favourites f
    JOIN properties p ON f.property_id = p.id
    LEFT JOIN scores s ON s.property_id = p.id
    LEFT JOIN enrichment_data e ON e.property_id = p.id
    ORDER BY s.total_score DESC NULLS LAST, p.price ASC
''').fetchall()

# Get gate results for each
gate_data = {}
for r in rows:
    pid = r[0]
    prop_id = conn.execute('SELECT id FROM properties WHERE portal_id = ?', (pid,)).fetchone()[0]
    gates = conn.execute(
        'SELECT gate_name, passed, reason FROM gate_results WHERE property_id = ?',
        (prop_id,),
    ).fetchall()
    gate_data[pid] = gates

print(f'=== YOUR {len(rows)} FAVOURITES - RANKED BY SCORE ===\n')

for i, r in enumerate(rows, 1):
    pid = r[0]
    score = r[22] or 0
    price = r[2]
    size = f"{r[3]:.0f} sqft" if r[3] else "? sqft"
    tenure = r[4] or "?"
    lease = f" ({r[5]}yr)" if r[5] else ""
    dom = r[13] or 0
    ct = r[8] or "?"
    epc = r[14] or "?"

    # Monthly mortgage (4.5%, 30yr)
    loan = price - 37500
    monthly_rate = 0.045 / 12
    num_payments = 360
    mortgage = (
        loan
        * (monthly_rate * (1 + monthly_rate) ** num_payments)
        / ((1 + monthly_rate) ** num_payments - 1)
        if loan > 0
        else 0
    )
    extras_monthly = ((r[6] or 0) + (r[7] or 0)) / 12
    ct_map = {"A": 91, "B": 109, "C": 127, "D": 145, "E": 181, "F": 218}
    ct_monthly = ct_map.get(ct, 109)
    total_housing = mortgage + extras_monthly + ct_monthly
    bills = 198
    total_allin = total_housing + bills

    if total_allin <= 993:
        tier = "GREEN"
    elif total_allin <= 1072:
        tier = "AMBER"
    elif total_allin <= 1200:
        tier = "STRETCH"
    else:
        tier = "RED"

    # 7% offer
    offer_price = int(price * 0.93)
    offer_loan = offer_price - 37500
    offer_mort = (
        offer_loan
        * (monthly_rate * (1 + monthly_rate) ** num_payments)
        / ((1 + monthly_rate) ** num_payments - 1)
        if offer_loan > 0
        else 0
    )
    offer_total = offer_mort + extras_monthly + ct_monthly + bills
    if offer_total <= 993:
        offer_tier = "GREEN"
    elif offer_total <= 1072:
        offer_tier = "AMBER"
    elif offer_total <= 1200:
        offer_tier = "STRETCH"
    else:
        offer_tier = "RED"

    # Gates
    gates = gate_data.get(pid, [])
    failed_gates = [g for g in gates if not g[1]]

    if not failed_gates and gates:
        gate_status = "QUALIFYING"
    elif len(failed_gates) <= 2:
        gate_status = f"NEAR MISS ({len(failed_gates)} fail)"
    elif not gates:
        gate_status = "NO GATES"
    else:
        gate_status = f"FAILS ({len(failed_gates)} gates)"

    # Score breakdown
    ff = r[16] or 0
    cs = r[17] or 0
    cp = r[18] or 0
    ll = r[19] or 0
    wk = r[20] or 0
    lt = r[21] or 0

    station = r[23] or "?"
    station_walk = f"{r[24]}min" if r[24] else "?"
    commute = f"{r[25]}min" if r[25] else "?"

    print("=" * 70)
    print(f"  #{i}  SCORE: {score:.1f}/100  |  {gate_status}  |  {tier}")
    print(f"  {r[1]}")
    print(f"  https://www.rightmove.co.uk/properties/{pid}")
    print(f"  GBP {price:,}  |  {size}  |  {tenure}{lease}  |  CT:{ct}  EPC:{epc}")
    print(f"  {r[10] or '?'} | {r[11] or '?'} bed | {dom} days listed")
    print(f"  Station: {station} ({station_walk} walk) | London commute: {commute}")
    print()
    print(
        f"  Scores: Financial:{ff:.0f}/30 Crime:{cs:.0f}/25 "
        f"Costs:{cp:.0f}/15 Layout:{ll:.0f}/15 Walk:{wk:.0f}/10 Flex:{lt:.0f}/5"
    )
    print(f"  At asking:  GBP{total_allin:,.0f}/mo all-in ({tier})")
    print(
        f"  At -7% offer (GBP{offer_price:,}):  "
        f"GBP{offer_total:,.0f}/mo all-in ({offer_tier})"
    )

    if failed_gates:
        reasons = ", ".join(g[0] + ": " + (g[2] or "") for g in failed_gates)
        print(f"  Failed gates: {reasons}")
    print()

conn.close()
