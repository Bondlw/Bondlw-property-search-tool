"""Analyse best options around Tunbridge Wells area specifically."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.database import Database
from src.storage.repository import PropertyRepository
from src.filtering.hard_gates import check_all_gates
from src.filtering.scoring import score_property
from src.utils.financial_calculator import FinancialCalculator
from src.config_loader import load_config

config = load_config()
db = Database()
repo = PropertyRepository(db)
calc = FinancialCalculator(config)

properties = repo.get_active_properties()
enrichment_map = {}
for prop in properties:
    enrichment = repo.get_enrichment(prop["id"])
    if enrichment:
        enrichment_map[prop["id"]] = enrichment

fav_ids = set(repo.get_favourite_ids())
excl_ids = set(repo.get_excluded_ids())

TAKE_HOME = 2650
BILLS = 198

# TW area filter
TW_KEYWORDS = [
    "tunbridge wells", "southborough", "paddock wood",
    "marden", "staplehurst", "high brooms", "pembury",
    "tonbridge", "rusthall", "langton green", "bidborough",
    "speldhurst", "royal tunbridge", "tn1", "tn2", "tn3", "tn4",
]

qualifying_tw = []
near_misses_tw = []


def is_tw_area(prop):
    addr = (prop.get("address") or "").lower()
    for kw in TW_KEYWORDS:
        if kw in addr:
            return True
    return False


def print_property(entry, show_failures=False, rank=None):
    fav_marker = " ★ FAV" if entry["is_fav"] else ""
    rank_str = f"{rank}. " if rank else "  "
    print(f"{rank_str}#{entry['id']} {entry['address']}{fav_marker}")
    print(
        f"     £{entry['price']:,.0f} | {entry['tenure']} | {entry['bedrooms']}bed "
        f"| Score: {entry['total_score']}/100"
    )
    mortgage = entry["costs"].get("mortgage_monthly", 0) or 0
    print(
        f"     Mortgage: £{mortgage:.0f}/mo | SC: £{entry['sc_pa']:.0f}/yr | "
        f"GR: £{entry['gr_pa']:.0f}/yr | CT({entry['ct_band']}): "
        f"£{entry['costs'].get('council_tax_monthly', 0) or 0:.0f}/mo"
    )
    print(
        f"     Housing: £{entry['housing_monthly']:.0f}/mo | "
        f"All-in: £{entry['all_in']:.0f}/mo ({entry['pct_income']:.1f}%) [{entry['status']}]"
    )
    lease = entry.get("lease_years")
    lease_str = f" | Lease: {lease}yr" if lease else ""
    print(f"     Station: {entry['station']} ({entry['station_min']}min) | Shop: {entry['shop_min']}min{lease_str}")

    if show_failures and entry["failures"]:
        print(f"     FAILED: {' | '.join(entry['failures'])}")

    # Score breakdown
    sc = entry["scores"]
    parts = []
    for key in ["financial_fit", "walkability", "crime_safety", "cost_predictability",
                "layout_livability", "long_term_flexibility"]:
        val = sc.get(key, {})
        if isinstance(val, dict):
            parts.append(f"{key.replace('_', ' ').title()}: {val.get('score', 0):.0f}")
        elif isinstance(val, (int, float)):
            parts.append(f"{key.replace('_', ' ').title()}: {val:.0f}")
    if parts:
        print(f"     Scores: {' | '.join(parts)}")
    print()


for prop in properties:
    pid = prop["id"]
    if pid in excl_ids:
        continue
    if not is_tw_area(prop):
        continue

    enrichment = enrichment_map.get(pid)
    passed, gate_results = check_all_gates(prop, enrichment, config)

    failed_gates = [g for g in gate_results if not g.passed]
    fail_count = len(failed_gates)

    scores = score_property(prop, enrichment, config)
    costs = calc.calculate_full_monthly_cost(prop)
    housing = costs.get("total_monthly", 0) or 0
    all_in = housing + BILLS
    pct = (all_in / TAKE_HOME) * 100
    status = "GREEN" if housing <= 795 else ("AMBER" if housing <= 950 else "RED")

    entry = {
        "id": pid,
        "address": prop.get("address", "?"),
        "price": prop.get("price", 0),
        "tenure": prop.get("tenure", "?"),
        "bedrooms": prop.get("bedrooms", "?"),
        "property_type": prop.get("property_type", "?"),
        "housing_monthly": housing,
        "all_in": all_in,
        "pct_income": pct,
        "status": status,
        "total_score": scores.get("total", 0),
        "scores": scores,
        "is_fav": pid in fav_ids,
        "failed_count": fail_count,
        "failures": [f"{g.gate_name}: {g.reason}" for g in failed_gates],
        "station": enrichment.get("nearest_station_name", "?") if enrichment else "?",
        "station_min": enrichment.get("nearest_station_walk_min", "?") if enrichment else "?",
        "shop_min": enrichment.get("nearest_supermarket_walk_min", "?") if enrichment else "?",
        "sc_pa": prop.get("service_charge_pa") or 0,
        "gr_pa": prop.get("ground_rent_pa") or 0,
        "ct_band": prop.get("council_tax_band") or "?",
        "lease_years": prop.get("lease_years"),
        "costs": costs,
    }

    if passed:
        qualifying_tw.append(entry)
    elif fail_count <= 2:
        near_misses_tw.append(entry)

qualifying_tw.sort(key=lambda x: (-x["total_score"], x["price"]))
near_misses_tw.sort(key=lambda x: (x["failed_count"], -x["total_score"], x["price"]))

print("=" * 75)
print(f"QUALIFYING AROUND TUNBRIDGE WELLS ({len(qualifying_tw)} properties)")
print("=" * 75)
for i, entry in enumerate(qualifying_tw, 1):
    print_property(entry, rank=i)

print("=" * 75)
print(f"NEAR MISSES AROUND TW ({len(near_misses_tw)} — failed 1-2 gates)")
print("=" * 75)
for i, entry in enumerate(near_misses_tw, 1):
    print_property(entry, show_failures=True, rank=i)

# Summary
print("=" * 75)
print("RECOMMENDATION SUMMARY")
print("=" * 75)
print(f"Qualifying: {len(qualifying_tw)} | Near misses: {len(near_misses_tw)}")
print()
if qualifying_tw:
    print("TOP 5 RECOMMENDATIONS:")
    for i, entry in enumerate(qualifying_tw[:5], 1):
        fav = " ★" if entry["is_fav"] else ""
        print(
            f"  {i}. #{entry['id']} {entry['address']}{fav} — "
            f"£{entry['price']:,.0f} | £{entry['housing_monthly']:.0f}/mo [{entry['status']}] | "
            f"Score: {entry['total_score']}/100"
        )
