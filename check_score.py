"""Quick check: Queripel scoring at asking vs offer price."""
import yaml
import sqlite3
from src.utils.financial_calculator import FinancialCalculator
from src.filtering.scoring import score_property

with open("config/search_config.yaml") as f:
    config = yaml.safe_load(f)

conn = sqlite3.connect("data/property_search.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT * FROM properties WHERE address LIKE '%Queripel%'")
row = cur.fetchone()
if row:
    prop = dict(row)
    print(f"Property: {prop['address']}")
    print(f"Asking: £{prop['price']:,.0f}")

    scores_ask = score_property(prop, None, config)
    print(f"\nScore at ASKING: {scores_ask['total']}/100")
    print(f"  Financial fit: {scores_ask['financial_fit']} — {scores_ask['financial_fit_reason']}")

    offer = round(prop["price"] * 0.93)
    offer_prop = {**prop, "price": offer}
    scores_off = score_property(offer_prop, None, config)
    print(f"\nScore at OFFER (£{offer:,.0f}, 7% off): {scores_off['total']}/100")
    print(f"  Financial fit: {scores_off['financial_fit']} — {scores_off['financial_fit_reason']}")
else:
    print("Queripel not found")
conn.close()
