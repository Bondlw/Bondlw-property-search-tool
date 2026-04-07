#!/usr/bin/env python3
"""Analyse specific shortlisted properties with full financial + size breakdown."""
import sqlite3
import re
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "property_search.db"
conn = sqlite3.connect(DB_PATH)

# Search terms from user's list
search_terms = [
    "queripel", "glendale", "springview", "garden road",
    "hawthorn", "liptraps", "duley", "dudley",
    "upper grosvenor", "silverdale", "mount pleasant",
    "sherwood", "pinewood", "woodbury", "queens road",
    "rosalind",
]

like_clauses = " OR ".join(f"LOWER(p.address) LIKE '%{t}%'" for t in search_terms)

rows = conn.execute(f'''
    SELECT p.portal_id, p.address, p.price, p.size_sqft, p.tenure, p.lease_years,
           p.service_charge_pa, p.ground_rent_pa, p.council_tax_band,
           p.is_active, p.property_type, p.bedrooms, p.bathrooms,
           p.days_on_market, p.epc_rating, p.postcode, p.description,
           s.total_score, s.financial_fit, s.crime_safety, s.cost_predictability,
           s.layout_livability, s.walkability, s.long_term_flexibility,
           e.nearest_station_name, e.nearest_station_walk_min,
           e.commute_to_london_min, e.crime_safety_score,
           e.nearest_supermarket_walk_min,
           (SELECT 1 FROM favourites f2 WHERE f2.property_id = p.id) as is_fav,
           p.id
    FROM properties p
    LEFT JOIN scores s ON s.property_id = p.id
    LEFT JOIN enrichment_data e ON e.property_id = p.id
    WHERE p.is_active = 1 AND ({like_clauses})
    ORDER BY p.price ASC
''').fetchall()

# Also try to extract size from description for properties without size_sqft
def extract_size_from_desc(desc):
    if not desc:
        return None, None
    # sq ft patterns
    sqft_match = re.search(r'(\d[\d,]*)\s*(?:sq\.?\s*ft|sqft|square\s*feet)', desc, re.I)
    sqm_match = re.search(r'(\d[\d,]*\.?\d*)\s*(?:sq\.?\s*m|sqm|square\s*met)', desc, re.I)
    sqft = None
    sqm = None
    if sqft_match:
        sqft = int(sqft_match.group(1).replace(',', ''))
    if sqm_match:
        sqm = float(sqm_match.group(1).replace(',', ''))
        if not sqft:
            sqft = int(sqm * 10.764)
    return sqft, sqm


print(f"Found {len(rows)} properties matching your shortlist\n")
print("=" * 80)

for r in rows:
    pid = r[0]
    price = r[2]
    db_size = r[3]
    desc = r[16]
    
    # Try to get size from description if not in DB
    desc_sqft, desc_sqm = extract_size_from_desc(desc)
    size_sqft = db_size or desc_sqft
    
    tenure = r[4] or "?"
    lease = f" ({r[5]}yr)" if r[5] else ""
    sc = r[6] or 0
    gr = r[7] or 0
    ct = r[8] or "?"
    epc = r[14] or "?"
    dom = r[13] or 0
    beds = r[11] or "?"
    baths = r[12] or "?"
    station = r[24] or "?"
    station_walk = r[25]
    commute = r[26]
    score = r[17] or 0
    is_fav = "★ FAV" if r[29] else ""
    
    # Monthly mortgage (4.5%, 30yr)
    loan = price - 37500
    monthly_rate = 0.045 / 12
    num_payments = 360
    mortgage = (
        loan * (monthly_rate * (1 + monthly_rate) ** num_payments) 
        / ((1 + monthly_rate) ** num_payments - 1)
        if loan > 0 else 0
    )
    extras_monthly = (sc + gr) / 12
    ct_map = {"A": 91, "B": 109, "C": 127, "D": 145, "E": 181, "F": 218}
    ct_monthly = ct_map.get(ct, 109)
    bills = 198
    total_allin = mortgage + extras_monthly + ct_monthly + bills

    if total_allin <= 993: tier = "GREEN"
    elif total_allin <= 1072: tier = "AMBER"
    elif total_allin <= 1200: tier = "STRETCH"
    else: tier = "RED"

    # 7% offer
    offer_price = int(price * 0.93)
    offer_loan = offer_price - 37500
    offer_mort = (
        offer_loan * (monthly_rate * (1 + monthly_rate) ** num_payments) 
        / ((1 + monthly_rate) ** num_payments - 1)
        if offer_loan > 0 else 0
    )
    offer_total = offer_mort + extras_monthly + ct_monthly + bills
    if offer_total <= 993: offer_tier = "GREEN"
    elif offer_total <= 1072: offer_tier = "AMBER"
    elif offer_total <= 1200: offer_tier = "STRETCH"
    else: offer_tier = "RED"

    # Size assessment
    if size_sqft:
        if size_sqft >= 590:
            size_verdict = f"GOOD ({size_sqft} sqft)"
        elif size_sqft >= 540:
            size_verdict = f"OK ({size_sqft} sqft - near minimum)"
        elif size_sqft >= 450:
            size_verdict = f"SMALL ({size_sqft} sqft - below min)"
        else:
            size_verdict = f"TINY ({size_sqft} sqft - too small)"
    else:
        size_verdict = "UNKNOWN - check floorplan"

    # Gate results
    prop_id = r[30]
    gates = conn.execute(
        'SELECT gate_name, passed, reason FROM gate_results WHERE property_id = ?',
        (prop_id,),
    ).fetchall()
    failed = [g for g in gates if not g[1]]
    if not failed and gates:
        gate_status = "QUALIFYING"
    elif not gates:
        gate_status = "NOT SCORED"
    else:
        gate_status = f"FAILS {len(failed)} gate(s)"

    print(f"  {r[1]}")
    print(f"  https://www.rightmove.co.uk/properties/{pid}")
    print(f"  {is_fav}")
    print(f"  Price: GBP {price:,}  |  {beds}bed {baths}bath  |  {r[10] or '?'}")
    print(f"  SIZE: {size_verdict}")
    print(f"  Tenure: {tenure}{lease}  |  SC: GBP{sc}/yr  GR: GBP{gr}/yr")
    print(f"  CT: {ct}  |  EPC: {epc}  |  Listed: {dom} days")
    print(f"  Station: {station} ({station_walk}min walk)" if station_walk else f"  Station: {station}")
    if commute:
        print(f"  London commute: {commute}min")
    print(f"  Score: {score:.1f}/100  |  Gates: {gate_status}")
    print(f"  ASKING:  GBP{total_allin:,.0f}/mo all-in  [{tier}]")
    print(f"  AT -7%:  GBP{offer_total:,.0f}/mo all-in  [{offer_tier}]  (offer GBP{offer_price:,})")
    if failed:
        for g in failed:
            print(f"    FAIL: {g[0]} — {g[2] or ''}")
    print("-" * 80)

# Summary table sorted by size
print("\n\n=== SUMMARY SORTED BY SIZE (best for 6ft+ comfort) ===\n")
sized = []
for r in rows:
    db_size = r[3]
    desc_sqft, _ = extract_size_from_desc(r[16])
    size = db_size or desc_sqft
    sized.append((size, r))

sized.sort(key=lambda x: (x[0] or 0), reverse=True)

print(f"{'Size':>10} {'Price':>10} {'Tier':>8} {'Offer Tier':>11} {'Tenure':>12} {'Fav':>5}  Address")
print("-" * 100)
for size, r in sized:
    price = r[2]
    loan = price - 37500
    monthly_rate = 0.045 / 12
    num_payments = 360
    mortgage = loan * (monthly_rate * (1 + monthly_rate) ** num_payments) / ((1 + monthly_rate) ** num_payments - 1) if loan > 0 else 0
    extras = ((r[6] or 0) + (r[7] or 0)) / 12
    ct_monthly = {"A": 91, "B": 109, "C": 127, "D": 145, "E": 181, "F": 218}.get(r[8] or "?", 109)
    total = mortgage + extras + ct_monthly + 198

    if total <= 993: tier = "GREEN"
    elif total <= 1072: tier = "AMBER"
    elif total <= 1200: tier = "STRETCH"
    else: tier = "RED"

    offer_loan = int(price * 0.93) - 37500
    offer_mort = offer_loan * (monthly_rate * (1 + monthly_rate) ** num_payments) / ((1 + monthly_rate) ** num_payments - 1) if offer_loan > 0 else 0
    offer_total = offer_mort + extras + ct_monthly + 198
    if offer_total <= 993: otier = "GREEN"
    elif offer_total <= 1072: otier = "AMBER"
    elif offer_total <= 1200: otier = "STRETCH"
    else: otier = "RED"

    fav = "★" if r[29] else ""
    sz = f"{size} sqft" if size else "? sqft"
    tenure = (r[4] or "?")[:12]
    lease_info = f"({r[5]}yr)" if r[5] else ""
    
    print(f"{sz:>10} {('GBP' + f'{price:,}'):>10} {tier:>8} {otier:>11} {tenure:>12}{lease_info:>7} {fav:>5}  {r[1][:50]}")

conn.close()
