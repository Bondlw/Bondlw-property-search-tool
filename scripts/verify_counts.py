"""Quick check: qualifying vs needs-verification counts after exclusions."""
import sqlite3
import sys
import yaml
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

with open(ROOT / "config" / "search_config.yaml") as f:
    config = yaml.safe_load(f)

from src.filtering.hard_gates import check_all_gates

db = sqlite3.connect(str(ROOT / "data" / "property_search.db"))
db.row_factory = sqlite3.Row

props = [dict(r) for r in db.execute("SELECT * FROM properties WHERE status = 'active'").fetchall()]
enrichments = {}
for r in db.execute("SELECT * FROM enrichment_data"):
    enrichments[r["property_id"]] = dict(r)

excluded_addr = config.get("excluded_address_terms", [])
qualifying = 0
needs_verify = 0
excluded_count = 0

for prop in props:
    addr = (prop.get("address") or prop.get("title") or "").lower()
    if any(t.lower() in addr for t in excluded_addr):
        excluded_count += 1
        continue
    enrichment = enrichments.get(prop["id"])
    passed, results = check_all_gates(prop, enrichment, config)
    if passed:
        has_unverified = any(g.needs_verification for g in results)
        if has_unverified:
            needs_verify += 1
        else:
            qualifying += 1

print(f"After excluding addresses ({', '.join(excluded_addr)}):")
print(f"  Excluded by address: {excluded_count}")
print(f"  Fully qualifying:    {qualifying}")
print(f"  Needs verification:  {needs_verify}")
print(f"  Total available:     {qualifying + needs_verify}")
