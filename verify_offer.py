from src.config_loader import load_config
from src.utils.financial_calculator import FinancialCalculator
import sqlite3

config = load_config()
calc = FinancialCalculator(config)
conn = sqlite3.connect('data/property_search.db')
conn.row_factory = sqlite3.Row

for pid in ['87629463', '163721603']:
    row = conn.execute('SELECT * FROM properties WHERE portal_id = ?', (pid,)).fetchone()
    prop = dict(row)
    neg = calc.calculate_negotiation_analysis(prop, days_on_market=35)
    address = prop["address"]
    print(f"{pid} ({address}):")
    print(f"  Asking: {prop['price']:,}")
    print(f"  Offer: {neg['suggested_offer']:,} ({neg['discount_pct']}% off)")
    print(f"  Would qualify: {neg['would_qualify']}")
    print(f"  Monthly at offer: {neg['offer_housing_monthly']:,.0f}")
    print(f"  Signals: {neg['signals']}")
    print(f"  Notes: {neg['notes']}")
    print()
conn.close()
