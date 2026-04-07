"""Check why Springview #1682 isn't qualifying."""
import sqlite3
import sys
import os
import yaml

project_root = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))
os.chdir(project_root)
from src.filtering.hard_gates import check_all_gates

conn = sqlite3.connect(
    os.path.join(os.path.dirname(__file__), "..", "data", "property_search.db")
)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get property
cur.execute("SELECT * FROM properties WHERE id = 1682")
prop = dict(cur.fetchone())

# Get enrichment
cur.execute("SELECT * FROM enrichment_data WHERE property_id = 1682")
row = cur.fetchone()
enrichment = dict(row) if row else None

# Load config
config_path = os.path.join(os.path.dirname(__file__), "..", "config", "search_config.yaml")
with open(config_path) as config_file:
    config = yaml.safe_load(config_file)

print(f"Property: {prop['address']}")
print(f"Postcode: {prop['postcode']}")
print(f"Price: £{prop['price']:,}")
print(f"SC: £{prop.get('service_charge_pa', 'N/A')}/yr")
print(f"GR: £{prop.get('ground_rent_pa', 'N/A')}/yr")
print(f"Lease: {prop.get('lease_years', 'N/A')} years")
print()

passed, results = check_all_gates(prop, enrichment, config)
print(f"Overall: {'PASS' if passed else 'FAIL'}")
print()
for gate_result in results:
    status = "PASS" if gate_result.passed else "FAIL"
    verification = " [needs verification]" if getattr(gate_result, "needs_verification", False) else ""
    print(f"  {gate_result.gate_name}: {status}{verification} — {gate_result.reason}")

conn.close()
