#!/usr/bin/env python3
"""Check qualification status of all favourite properties."""

import sqlite3
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "data" / "property_search.db"

import sys
sys.path.insert(0, str(REPO_ROOT))

from src.config_loader import load_config
from src.filtering.hard_gates import check_all_gates
from src.utils.financial_calculator import FinancialCalculator


def main():
    config = load_config()
    calc = FinancialCalculator(config)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT p.*, f.notes, f.added_at
        FROM favourites f
        JOIN properties p ON p.id = f.property_id
        WHERE p.status = 'active'
        ORDER BY f.added_at DESC
    """).fetchall()

    print(f"Total active favourites: {len(rows)}\n")

    for r in rows:
        prop = dict(r)
        enrichment_row = conn.execute(
            "SELECT * FROM enrichment_data WHERE property_id = ?", (prop["id"],)
        ).fetchone()
        enrichment = dict(enrichment_row) if enrichment_row else {}

        costs = calc.calculate_full_monthly_cost(prop)
        prop["_costs"] = costs

        passed, gate_results = check_all_gates(prop, enrichment, config)
        has_unverified = any(g.needs_verification for g in gate_results)

        first = prop.get("first_listed_date") or prop.get("first_seen_date")
        days = None
        if first:
            try:
                dt = datetime.strptime(first[:10], "%Y-%m-%d").date()
                days = (date.today() - dt).days
            except (ValueError, TypeError):
                pass

        neg = calc.calculate_negotiation_analysis(prop, days)

        if passed and not has_unverified:
            status = "✓ QUALIFIES at asking"
            offer_info = ""
        elif passed and has_unverified:
            unverified_names = [g.gate_name for g in gate_results if g.needs_verification]
            status = "⚠ QUALIFIES (unverified)"
            offer_info = " — verify: " + ", ".join(unverified_names)
        elif neg and neg.get("would_qualify"):
            offer_price = neg["suggested_offer"]
            pct = neg["discount_pct"]
            saving = neg["saving"]
            status = f"✓ QUALIFIES at offer £{offer_price // 1000}k (-{pct}%)"
            offer_info = f" — save £{saving:,}"
        else:
            failed_names = [g.gate_name for g in gate_results if not g.passed]
            status = "✗ DOES NOT QUALIFY"
            offer_info = " — fails: " + ", ".join(failed_names)

        addr = (prop.get("address") or prop.get("title") or "")[:45]
        print(f"#{prop['id']:>4}  £{prop['price']:>7,}  {addr:<45}")
        print(f"       {status}{offer_info}")
        rating = costs["affordability_rating"].upper()
        print(f"       Housing: £{costs['total_monthly']:,.0f}/mo  All-in: £{costs['total_all_in_monthly']:,.0f}/mo  ({rating})")
        if neg:
            print(f"       Offer: £{neg['suggested_offer']:,} (-{neg['discount_pct']}%) → All-in £{neg['offer_all_in_monthly']:,.0f}/mo")
        print()

    conn.close()


if __name__ == "__main__":
    main()
