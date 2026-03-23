"""Analyse favourites with full financial breakdown and gate status."""
from src.storage.database import Database

db = Database("data/property_search.db")

# Get favourites with enrichment and scores
rows = db.conn.execute("""
    SELECT p.id, p.address, p.price, p.bedrooms, p.property_type,
           p.epc_rating, p.council_tax_band, p.tenure,
           p.service_charge_pa, p.ground_rent_pa, p.lease_years,
           p.price_reduced, p.size_sqft, p.days_on_market,
           e.nearest_station_name, e.nearest_station_walk_min,
           e.nearest_supermarket_name, e.nearest_supermarket_walk_min,
           e.flood_zone, e.council_tax_annual_estimate,
           e.commute_to_london_min, e.annual_season_ticket,
           s.total_score, s.financial_fit, s.walkability,
           s.crime_safety, s.cost_predictability, s.layout_livability,
           s.long_term_flexibility
    FROM properties p
    INNER JOIN favourites f ON p.id = f.property_id
    LEFT JOIN enrichment_data e ON p.id = e.property_id
    LEFT JOIN scores s ON p.id = s.property_id
    WHERE p.is_active = 1
    ORDER BY COALESCE(s.total_score, 0) DESC
""").fetchall()

print(f"=== {len(rows)} FAVOURITES (sorted by score) ===\n")

for r in rows:
    d = dict(r)
    pid = d["id"]

    # Get gate failures for this property
    gates = db.conn.execute(
        "SELECT gate_name, passed, reason FROM gate_results WHERE property_id = ?",
        (pid,),
    ).fetchall()
    failed_gates = [dict(g) for g in gates if not g["passed"]]
    passed_count = sum(1 for g in gates if g["passed"])
    total_gates = len(gates)

    sc = d["service_charge_pa"] or 0
    gr = d["ground_rent_pa"] or 0
    lease = d["lease_years"] or "-"
    epc = d["epc_rating"] or "?"
    ct = d["council_tax_band"] or "?"
    tenure = d["tenure"] or "?"
    stn_name = d["nearest_station_name"] or "?"
    stn_min = d["nearest_station_walk_min"] or "?"
    shop_name = d["nearest_supermarket_name"] or "?"
    shop_min = d["nearest_supermarket_walk_min"] or "?"
    score = d["total_score"] or 0
    reduced = "REDUCED" if d["price_reduced"] else ""
    sqft = d["size_sqft"] or "?"
    dom = d["days_on_market"] or "?"
    london = d["commute_to_london_min"] or "?"
    ct_est = d["council_tax_annual_estimate"] or "?"
    flood = d["flood_zone"] or "?"
    addr = (d["address"] or "?")[:55]
    price = d["price"]
    beds = d["bedrooms"]

    # Calculate monthly housing cost estimate
    # Mortgage: price - 37500 deposit, 4.5%, 30yr
    loan = price - 37500
    monthly_rate = 0.045 / 12
    num_payments = 30 * 12
    if loan > 0 and monthly_rate > 0:
        mortgage_monthly = loan * (monthly_rate * (1 + monthly_rate) ** num_payments) / ((1 + monthly_rate) ** num_payments - 1)
    else:
        mortgage_monthly = 0
    sc_monthly = sc / 12
    gr_monthly = gr / 12
    ct_monthly = (ct_est / 12) if isinstance(ct_est, (int, float)) else 0
    housing_monthly = mortgage_monthly + sc_monthly + gr_monthly + ct_monthly
    all_in_monthly = housing_monthly + 198  # bills

    gate_status = "PASS" if total_gates > 0 and len(failed_gates) == 0 else f"FAIL({len(failed_gates)})"

    print(f"{'='*70}")
    print(f"  #{pid} SCORE: {score:.0f}/100  |  Gates: {gate_status} ({passed_count}/{total_gates})  |  {reduced}")
    print(f"  {addr}")
    print(f"  Price: £{price:,}  |  {beds}bed  |  {tenure}  |  Lease: {lease}yr  |  {sqft} sqft")
    print(f"  EPC: {epc}  |  CT: {ct} (£{ct_est}/yr)  |  SC: £{sc:,.0f}/yr  |  GR: £{gr:,.0f}/yr  |  Flood: {flood}")
    print(f"  Station: {stn_name} ({stn_min}min)  |  Shop: {shop_name} ({shop_min}min)  |  London: {london}min")
    print(f"  >>> MONTHLY: Mortgage £{mortgage_monthly:.0f} + SC £{sc_monthly:.0f} + GR £{gr_monthly:.0f} + CT £{ct_monthly:.0f} = Housing £{housing_monthly:.0f} | All-in £{all_in_monthly:.0f}")
    if housing_monthly > 0:
        pct = (all_in_monthly / 2650) * 100
        rag = "GREEN" if housing_monthly <= 795 else ("AMBER" if housing_monthly <= 950 else "RED")
        print(f"  >>> {rag} | {pct:.1f}% of take-home | Max housing: £950 | Max all-in: £1,148")
    if failed_gates:
        reasons = "; ".join(f"{g['gate_name']}: {g['reason']}" for g in failed_gates)
        print(f"  >>> FAILED GATES: {reasons}")
    print()
