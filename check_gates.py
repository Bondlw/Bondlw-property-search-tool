import sqlite3
import json
import sys
sys.path.insert(0, '.')

from src.config_loader import load_config
from src.utils.financial_calculator import FinancialCalculator
from src.filtering.hard_gates import check_all_gates

config = load_config()
calc = FinancialCalculator(config)

conn = sqlite3.connect('data/property_search.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

ids = ['87629463', '171409649', '163721603']
for pid in ids:
    cur.execute("SELECT * FROM properties WHERE portal_id = ?", (pid,))
    row = cur.fetchone()
    if not row:
        print(f'\n=== {pid} === NOT FOUND')
        continue
    
    prop = dict(row)
    print(f'\n{"="*60}')
    print(f'Property {pid}: {prop["address"]}')
    print(f'Price: £{prop["price"]:,}')
    print(f'Type: {prop["property_type"]}, Tenure: {prop["tenure"]}')
    print(f'Lease: {prop["lease_years"]} years')
    print(f'Service charge: £{prop["service_charge_pa"]}/yr' if prop["service_charge_pa"] else 'Service charge: None')
    print(f'Ground rent: £{prop["ground_rent_pa"]}/yr' if prop["ground_rent_pa"] is not None else 'Ground rent: None')
    
    # Calculate mortgage
    deposit = config['user']['deposit']
    mortgage_amount = prop['price'] - deposit
    if mortgage_amount > 0:
        rate = config['user']['mortgage_rate'] / 100 / 12
        term = config['user']['mortgage_term_years'] * 12
        monthly_mortgage = mortgage_amount * (rate * (1 + rate)**term) / ((1 + rate)**term - 1)
    else:
        monthly_mortgage = 0
    
    monthly_sc = (prop['service_charge_pa'] or 0) / 12
    monthly_gr = (prop['ground_rent_pa'] or 0) / 12
    monthly_total = monthly_mortgage + monthly_sc + monthly_gr
    
    print(f'\nMortgage amount: £{mortgage_amount:,.0f}')
    print(f'Monthly mortgage: £{monthly_mortgage:,.2f}')
    print(f'Monthly service charge: £{monthly_sc:,.2f}')
    print(f'Monthly ground rent: £{monthly_gr:,.2f}')
    print(f'Monthly total (housing): £{monthly_total:,.2f}')
    
    # Check against tiers
    targets = config['monthly_target']
    print(f'\nTier thresholds: GREEN ≤£{targets["min"]}, AMBER ≤£{targets["recommended"]}, STRETCH ≤£{targets["max"]}')
    if monthly_mortgage <= targets['min']:
        print(f'Mortgage tier: GREEN')
    elif monthly_mortgage <= targets['recommended']:
        print(f'Mortgage tier: AMBER')
    elif monthly_mortgage <= targets['max']:
        print(f'Mortgage tier: STRETCH')
    else:
        print(f'Mortgage tier: RED (EXCEEDS MAX)')
    
    # Run hard gates
    all_passed, gate_results = check_all_gates(prop, None, config)
    print(f'\nHard gates: {"ALL PASSED" if all_passed else "FAILED"}')
    for result in gate_results:
        status = 'PASS' if result.passed else 'FAIL'
        if not result.passed:
            print(f'  ❌ {result.gate_name}: {result.reason}')
        else:
            print(f'  ✅ {result.gate_name}')

conn.close()
