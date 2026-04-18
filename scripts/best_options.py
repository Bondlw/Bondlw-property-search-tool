"""Analyse best property options from the database."""
import sqlite3
import math

conn = sqlite3.connect("data/property_search.db")
conn.row_factory = sqlite3.Row

DEPOSIT = 0        # Update to match user.deposit in search_config.yaml
RATE = 0.045
TERM_YEARS = 30
TAKE_HOME = 0      # Update to match user.monthly_take_home in search_config.yaml
BILLS = 198
GREEN_MAX = 795
AMBER_MAX = 874
STRETCH_MAX = 954
CT_MAP = {"A": 94, "B": 109, "C": 125, "D": 140, "E": 171}


def calc_mortgage(price):
    principal = max(price - DEPOSIT, 0)
    monthly_rate = RATE / 12
    n_payments = TERM_YEARS * 12
    if monthly_rate > 0 and principal > 0:
        return principal * (monthly_rate * (1 + monthly_rate) ** n_payments) / (
            (1 + monthly_rate) ** n_payments - 1
        )
    return 0


def format_property(row):
    price = row["price"] or 0
    sc = row["service_charge_pa"] or 0
    gr = row["ground_rent_pa"] or 0
    mortgage = calc_mortgage(price)
    ct_band = row["council_tax_band"] or "?"
    ct_mo = CT_MAP.get(ct_band, 0)
    housing = mortgage + sc / 12 + gr / 12 + ct_mo
    all_in = housing + BILLS
    pct = (all_in / TAKE_HOME) * 100
    status = "GREEN" if housing <= GREEN_MAX else ("AMBER" if housing <= AMBER_MAX else ("STRETCH" if housing <= STRETCH_MAX else "RED"))

    lines = []
    pid = row["id"]
    addr = row["address"]
    lines.append(f"  #{pid} {addr}")
    lines.append(
        f"     Price: £{price:,.0f} | {row['tenure']} | {row['bedrooms']}bed "
        f"| Score: {row['total_score']}/100 | Fav: {row['is_fav']}"
    )
    lines.append(
        f"     Mortgage: £{mortgage:.0f}/mo | SC: £{sc:.0f}/yr | GR: £{gr:.0f}/yr | CT({ct_band}): £{ct_mo}/mo"
    )
    lines.append(
        f"     Housing: £{housing:.0f}/mo | All-in: £{all_in:.0f}/mo ({pct:.1f}%) [{status}]"
    )
    station = row["nearest_station_name"] or "?"
    station_min = row["nearest_station_walk_min"] or "?"
    shop_min = row["nearest_supermarket_walk_min"] or "?"
    lines.append(f"     Station: {station} ({station_min}min) | Shop: {shop_min}min")
    return "\n".join(lines), housing


# === QUALIFYING ===
print("=" * 70)
print("QUALIFYING PROPERTIES (all gates passed)")
print("=" * 70)
qualifying = conn.execute(
    """
    SELECT p.id, p.address, p.price, p.property_type, p.bedrooms, p.tenure,
           p.service_charge_pa, p.ground_rent_pa, p.lease_years,
           e.nearest_station_name, e.nearest_station_walk_min,
           e.nearest_supermarket_walk_min, p.council_tax_band,
           s.total_score, s.financial_fit, s.walkability, s.crime_safety,
           s.cost_predictability, s.layout_livability, s.long_term_flexibility,
           CASE WHEN f.property_id IS NOT NULL THEN 'YES' ELSE 'no' END as is_fav
    FROM properties p
    LEFT JOIN enrichment_data e ON p.id = e.property_id
    LEFT JOIN scores s ON p.id = s.property_id
    LEFT JOIN favourites f ON p.id = f.property_id
    WHERE p.id NOT IN (SELECT property_id FROM exclusions)
    AND p.id NOT IN (
        SELECT DISTINCT property_id FROM gate_results WHERE passed = 0
    )
    AND p.id IN (SELECT DISTINCT property_id FROM gate_results)
    ORDER BY s.total_score DESC, p.price ASC
    """
).fetchall()

for row in qualifying:
    text, _ = format_property(row)
    print(text)
    print()

print(f"Total qualifying: {len(qualifying)}\n")

# === NEAR MISSES ===
print("=" * 70)
print("NEAR MISSES (failed 1-2 gates)")
print("=" * 70)
near_misses = conn.execute(
    """
    SELECT p.id, p.address, p.price, p.property_type, p.bedrooms, p.tenure,
           p.service_charge_pa, p.ground_rent_pa, p.lease_years,
           e.nearest_station_name, e.nearest_station_walk_min,
           e.nearest_supermarket_walk_min, p.council_tax_band,
           s.total_score,
           GROUP_CONCAT(gr2.gate_name || ': ' || gr2.reason, ' | ') as failures,
           CASE WHEN f.property_id IS NOT NULL THEN 'YES' ELSE 'no' END as is_fav
    FROM properties p
    LEFT JOIN enrichment_data e ON p.id = e.property_id
    LEFT JOIN scores s ON p.id = s.property_id
    LEFT JOIN favourites f ON p.id = f.property_id
    INNER JOIN gate_results gr2 ON p.id = gr2.property_id AND gr2.passed = 0
    WHERE p.id NOT IN (SELECT property_id FROM exclusions)
    GROUP BY p.id
    HAVING COUNT(gr2.gate_name) <= 2
    ORDER BY COUNT(gr2.gate_name) ASC, s.total_score DESC, p.price ASC
    """
).fetchall()

for row in near_misses:
    text, _ = format_property(row)
    print(text)
    print(f"     FAILED: {row['failures']}")
    print()

print(f"Total near misses: {len(near_misses)}\n")

# === CURRENT FAVOURITES ===
print("=" * 70)
print("CURRENT FAVOURITES")
print("=" * 70)
favs = conn.execute(
    """
    SELECT p.id, p.address, p.price, p.property_type, p.bedrooms, p.tenure,
           p.service_charge_pa, p.ground_rent_pa, p.lease_years,
           e.nearest_station_name, e.nearest_station_walk_min,
           e.nearest_supermarket_walk_min, p.council_tax_band,
           s.total_score,
           'YES' as is_fav
    FROM properties p
    INNER JOIN favourites f ON p.id = f.property_id
    LEFT JOIN enrichment_data e ON p.id = e.property_id
    LEFT JOIN scores s ON p.id = s.property_id
    ORDER BY s.total_score DESC, p.price ASC
    """
).fetchall()

for row in favs:
    text, _ = format_property(row)
    print(text)
    print()

print(f"Total favourites: {len(favs)}")
conn.close()
