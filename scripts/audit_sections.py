"""Precise audit of report section counts using the actual report generator logic."""

import sys
sys.path.insert(0, ".")

from src.storage.database import Database
from src.storage.repository import PropertyRepository
from src.config_loader import load_config
from src.reporting.report_generator import ReportGenerator

config = load_config()
db = Database()
repo = PropertyRepository(db)

# Get all data exactly as the CLI does
properties = repo.get_active_properties()
enrichment_map = {}
for prop in properties:
    e = repo.get_enrichment(prop["id"])
    if e:
        enrichment_map[prop["id"]] = e
favourite_ids = set(repo.get_favourite_ids())
excluded_ids = set(repo.get_excluded_ids())

print(f"Input: {len(properties)} active properties")
print(f"Favourites: {favourite_ids}")
print(f"Excluded: {excluded_ids}")
print()

# Run the report generator to classify properties
gen = ReportGenerator(config)

# We need to intercept the classification. Let's replicate the logic.
from datetime import date
from src.filtering.hard_gates import check_all_gates
from src.filtering.scoring import score_property
from src.utils.financial_calculator import FinancialCalculator

today = date.today().isoformat()
calc = FinancialCalculator(config)

qualifying = []
needs_verification = []
near_misses = []
new_today = []
opportunities_negotiation = []
opportunities_stretch = []
favourites = []
radius_skipped = 0
excluded_skipped = 0
location_excluded = 0

for prop in properties:
    prop_id = prop["id"]
    prop["_is_favourite"] = prop_id in favourite_ids
    prop["_is_excluded"] = prop_id in excluded_ids
    
    enrichment = enrichment_map.get(prop_id)
    
    # Radius filter
    lat = prop.get("latitude")
    lng = prop.get("longitude")
    if lat and lng:
        area_name, area_dist = gen._nearest_area(lat, lng)
        prop["_search_area"] = area_name
        max_radius = config.get("max_radius_miles", 10)
        if area_dist > max_radius:
            radius_skipped += 1
            continue
    else:
        prop["_search_area"] = "Unknown"
    
    # Excluded location filter
    excluded_locations = config.get("excluded_address_terms", [])
    addr_lower = (prop.get("address") or prop.get("title") or "").lower()
    if any(term.lower() in addr_lower for term in excluded_locations):
        location_excluded += 1
        continue
    
    # Skip excluded
    if prop["_is_excluded"]:
        excluded_skipped += 1
        continue
    
    passed, gate_results = check_all_gates(prop, enrichment, config)
    failed_gates = [g for g in gate_results if not g.passed]
    
    prop["_costs"] = calc.calculate_full_monthly_cost(prop)
    prop["_gate_results"] = gate_results
    prop["_failed_gates"] = failed_gates
    
    # New today
    if prop.get("first_seen_date") == today:
        new_today.append(prop)
    
    # Favourites go to their own section
    if prop["_is_favourite"]:
        if passed:
            has_unverified = any(g.needs_verification for g in gate_results)
            prop["_gate_status"] = "needs-verify" if has_unverified else "qualifying"
        else:
            prop["_gate_status"] = "failed"
        favourites.append(prop)
        continue
    
    # Non-favourited classification
    if passed:
        has_unverified = any(g.needs_verification for g in gate_results)
        if has_unverified:
            needs_verification.append(prop)
        else:
            qualifying.append(prop)
            if passed:
                prop["_scores"] = score_property(prop, enrichment, config)
    else:
        neg_check = calc.calculate_negotiation_analysis(prop, None)
        offer_qualifies = neg_check and neg_check.get("would_qualify")
        asking_rating = (prop.get("_costs") or {}).get("affordability_rating", "red")
        if len(failed_gates) <= 2 and offer_qualifies and asking_rating != "red":
            near_misses.append(prop)

# Count qualifying favourites for hero stat
qualifying_fav_count = sum(1 for p in favourites if p.get("_gate_status") == "qualifying")

print("=" * 70)
print("REPORT SECTION AUDIT")
print("=" * 70)
print(f"\nRadius skipped: {radius_skipped}")
print(f"Location excluded: {location_excluded}")
print(f"User excluded: {excluded_skipped}")
print()

print("--- HERO STATS (what shows in the summary bar) ---")
print(f"  Tracked: {len(properties) - radius_skipped}  (i.e. in-radius)")
print(f"  Qualifying: {len(qualifying) + qualifying_fav_count}  (section qualifying + qualifying favourites)")
print(f"  Needs Verifying: {len(needs_verification)}")
print(f"  New Today: {len(new_today)}")
print(f"  Favourites: {len(favourites)}")
print()

print("--- SECTION COUNTS (what shows on section headers) ---")
print(f"  Shortlisted: 0  (not tracked here)")
print(f"  Favourites ({len(favourites)}):")
for p in favourites:
    gate = p.get("_gate_status", "?")
    print(f"    #{p['id']} {p.get('address', '?')[:50]} — £{p.get('price', 0):,} — gate_status={gate}")

print(f"\n  Qualifying ({len(qualifying)}):")
for p in qualifying:
    score = (p.get("_scores") or {}).get("total", "?")
    print(f"    #{p['id']} {p.get('address', '?')[:50]} — £{p.get('price', 0):,} — score={score}")

print(f"\n  Needs Verification ({len(needs_verification)}):")
for p in needs_verification:
    failed = [g.gate_name for g in p.get("_failed_gates", [])]
    unverified = [g.gate_name for g in p.get("_gate_results", []) if g.needs_verification]
    print(f"    #{p['id']} {p.get('address', '?')[:50]} — £{p.get('price', 0):,} — unverified: {unverified}")

print(f"\n  Near Misses ({len(near_misses)}):")
for p in near_misses:
    failed = [g.gate_name for g in p.get("_failed_gates", [])]
    print(f"    #{p['id']} {p.get('address', '?')[:50]} — £{p.get('price', 0):,} — failed: {failed}")

print(f"\n  New Today ({len(new_today)}):")
for p in new_today:
    print(f"    #{p['id']} {p.get('address', '?')[:50]} — £{p.get('price', 0):,}")

print()
print("--- CONSISTENCY CHECK ---")
# The hero Qualifying count includes qualifying favourites, but the section header only shows non-favourite qualifying
hero_qualifying = len(qualifying) + qualifying_fav_count
section_qualifying = len(qualifying)
if hero_qualifying != section_qualifying:
    print(f"  ⚠ Hero 'Qualifying' = {hero_qualifying} but Qualifying section shows ({section_qualifying})")
    print(f"    → {qualifying_fav_count} qualifying properties are in the Favourites section instead")
    print(f"    → This is BY DESIGN — favourites are pulled into their own section")
else:
    print(f"  ✓ Qualifying: hero and section both show {hero_qualifying}")

# Check no property appears in both favourites AND another section
fav_ids_set = {p["id"] for p in favourites}
qual_ids = {p["id"] for p in qualifying}
nv_ids = {p["id"] for p in needs_verification}
nm_ids = {p["id"] for p in near_misses}

overlap_qual = fav_ids_set & qual_ids
overlap_nv = fav_ids_set & nv_ids
overlap_nm = fav_ids_set & nm_ids

if overlap_qual or overlap_nv or overlap_nm:
    print(f"  ✗ OVERLAP! Favourites overlap with:")
    if overlap_qual: print(f"    Qualifying: {overlap_qual}")
    if overlap_nv: print(f"    Needs Verification: {overlap_nv}")
    if overlap_nm: print(f"    Near Misses: {overlap_nm}")
else:
    print(f"  ✓ No overlap — favourites don't appear in other sections")

print()
print("--- FAVOURITES DETAIL ---")
for p in favourites:
    gate = p.get("_gate_status", "?")
    costs = p.get("_costs", {})
    rating = costs.get("affordability_rating", "?")
    monthly = costs.get("total_monthly", 0)
    all_in = costs.get("total_all_in_monthly", 0)
    print(f"  #{p['id']} {p.get('address', '?')[:45]} — £{p.get('price', 0):,} — {gate} — £{monthly:.0f}/mo housing — £{all_in:.0f}/mo all-in — {rating}")
