"""One-off diagnostic: show which gates are filtering out properties."""
import sqlite3
import json
import sys
import yaml
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

with open(ROOT / "config" / "search_config.yaml") as f:
    config = yaml.safe_load(f)

from src.filtering.hard_gates import check_all_gates
from src.utils.financial_calculator import FinancialCalculator

db = sqlite3.connect(str(ROOT / "data" / "property_search.db"))
db.row_factory = sqlite3.Row

props = [dict(r) for r in db.execute("SELECT * FROM properties WHERE status = 'active'").fetchall()]
enrichments = {}
for r in db.execute("SELECT * FROM enrichment_data"):
    enrichments[r["property_id"]] = dict(r)

print(f"Total active properties in DB: {len(props)}")
print()

gate_fail_counts = Counter()
gate_fail_examples: dict[str, list[str]] = {}
total_pass = 0
total_fail = 0
fail_combos = Counter()

for prop in props:
    enrichment = enrichments.get(prop["id"])
    passed, results = check_all_gates(prop, enrichment, config)
    if passed:
        total_pass += 1
    else:
        total_fail += 1
        failed = [r for r in results if not r.passed]
        for f in failed:
            gate_fail_counts[f.gate_name] += 1
            examples = gate_fail_examples.setdefault(f.gate_name, [])
            if len(examples) < 3:
                addr = (prop.get("address") or "?")[:50]
                examples.append(f"{addr}: {f.reason}")
        combo = "+".join(sorted(set(f.gate_name for f in failed)))
        fail_combos[combo] += 1

print(f"QUALIFYING (all gates pass): {total_pass}")
print(f"REJECTED (1+ gate fails):    {total_fail}")
print()

print("=== GATE FAILURE BREAKDOWN (most common first) ===")
for gate, count in gate_fail_counts.most_common():
    pct = round(count / len(props) * 100, 1) if props else 0
    print(f"  {gate:25s}  {count:4d} properties ({pct}%)")

print()
print("=== TOP FAILURE COMBINATIONS ===")
for combo, count in fail_combos.most_common(15):
    print(f"  {count:3d}x  {combo}")

print()
print("=== EXAMPLE FAILURE REASONS ===")
for gate, examples in sorted(gate_fail_examples.items()):
    print(f"  [{gate}]")
    for ex in examples:
        print(f"    - {ex}")

# Monthly cost distribution
print()
print("=== MONTHLY COST DISTRIBUTION ===")
calc = FinancialCalculator(config)
costs = []
for prop in props:
    c = calc.calculate_total_monthly(prop)
    costs.append((c["total_monthly"], prop.get("address", "?")[:40], prop.get("price", 0)))

costs.sort(key=lambda x: x[0])
brackets = [
    ("Under £795 (GREEN)", lambda m: m <= 795),
    ("£795-£928 (AMBER)", lambda m: 795 < m <= 928),
    ("£928-£1100", lambda m: 928 < m <= 1100),
    ("£1100-£1271", lambda m: 1100 < m <= 1271),
    ("Over £1271", lambda m: m > 1271),
]
for label, test in brackets:
    n = sum(1 for m, _, _ in costs if test(m))
    print(f"  {label:25s}  {n:4d} properties")

print()
print("=== PROPERTIES THAT WOULD QUALIFY IF GREEN RAISED TO £950 (£1,148 all-in) ===")
newly_qualifying = 0
for prop in props:
    enrichment = enrichments.get(prop["id"])
    # Temporarily test with raised green
    config_copy = dict(config)
    config_copy["monthly_target"] = {"min": 950, "max": 1000}
    passed_new, _ = check_all_gates(prop, enrichment, config_copy)

    # Check if it passes with new green but failed with old
    passed_old, _ = check_all_gates(prop, enrichment, config)
    if passed_new and not passed_old:
        newly_qualifying += 1
        c = calc.calculate_total_monthly(prop)
        addr = (prop.get("address") or "?")[:50]
        print(f"  + {addr}  £{prop.get('price',0):,}  £{c['total_monthly']:,.0f}/mo")

print(f"\n  {newly_qualifying} additional properties would qualify")
