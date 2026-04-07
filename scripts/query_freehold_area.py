"""Find all freehold properties in the wider TW/Maidstone/Snodland area."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "property_search.db"

DEPOSIT = 37500
RATE = 0.045
TERM_MONTHS = 360
CT_BANDS = {"A": 91, "B": 109, "C": 127, "D": 145, "E": 163}
BILLS = 198
GREEN = 993
AMBER = 1072
STRETCH = 1200
OFFER_DISCOUNT = 0.07

rate_monthly = RATE / 12


def calculate_monthly(purchase_price, council_tax_band, service_charge_pa, ground_rent_pa):
    mortgage_amount = max(purchase_price - DEPOSIT, 0)
    if mortgage_amount > 0:
        monthly_mortgage = mortgage_amount * (
            rate_monthly * (1 + rate_monthly) ** TERM_MONTHS
        ) / ((1 + rate_monthly) ** TERM_MONTHS - 1)
    else:
        monthly_mortgage = 0
    council_tax_monthly = CT_BANDS.get(council_tax_band, 127)
    service_charge_monthly = (service_charge_pa or 0) / 12
    ground_rent_monthly = (ground_rent_pa or 0) / 12
    return monthly_mortgage + BILLS + council_tax_monthly + service_charge_monthly + ground_rent_monthly


def get_tier(total_monthly):
    if total_monthly <= GREEN:
        return "GREEN"
    elif total_monthly <= AMBER:
        return "AMBER"
    elif total_monthly <= STRETCH:
        return "STRETCH"
    return "RED"


conn = sqlite3.connect(DB_PATH)

rows = conn.execute(
    """
    SELECT p.portal_id, p.address, p.price, p.property_type, p.tenure, p.bedrooms,
           p.size_sqft, p.council_tax_band, p.service_charge_pa, p.ground_rent_pa,
           p.title,
           CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END as is_fav
    FROM properties p
    LEFT JOIN favourites f ON f.property_id = p.id
    WHERE p.status = 'active'
    AND (LOWER(p.tenure) LIKE '%freehold%' OR LOWER(p.tenure) LIKE '%share_of_freehold%')
    AND LOWER(p.property_type) NOT LIKE '%flat%'
    AND (
        LOWER(p.address) LIKE '%tunbridge wells%' OR LOWER(p.address) LIKE '%royal tunbridge%'
        OR LOWER(p.address) LIKE '%maidstone%' OR LOWER(p.address) LIKE '%snodland%'
        OR LOWER(p.address) LIKE '%tonbridge%' OR LOWER(p.address) LIKE '%borough green%'
        OR LOWER(p.address) LIKE '%east malling%' OR LOWER(p.address) LIKE '%west malling%'
        OR LOWER(p.address) LIKE '%aylesford%' OR LOWER(p.address) LIKE '%ditton%'
        OR LOWER(p.address) LIKE '%larkfield%' OR LOWER(p.address) LIKE '%paddock wood%'
        OR LOWER(p.address) LIKE '%southborough%' OR LOWER(p.address) LIKE '%pembury%'
        OR LOWER(p.address) LIKE '%crowborough%' OR LOWER(p.address) LIKE '%sevenoaks%'
        OR LOWER(p.address) LIKE '%hildenborough%' OR LOWER(p.address) LIKE '%hadlow%'
        OR LOWER(p.address) LIKE '%headcorn%' OR LOWER(p.address) LIKE '%staplehurst%'
        OR LOWER(p.address) LIKE '%bearsted%' OR LOWER(p.address) LIKE '%penenden%'
        OR LOWER(p.address) LIKE '%barming%' OR LOWER(p.address) LIKE '%wateringbury%'
        OR LOWER(p.address) LIKE '%yalding%' OR LOWER(p.address) LIKE '%east peckham%'
        OR LOWER(p.address) LIKE '%five oak green%' OR LOWER(p.address) LIKE '%matfield%'
        OR LOWER(p.address) LIKE '%brenchley%' OR LOWER(p.address) LIKE '%lamberhurst%'
        OR LOWER(p.address) LIKE '%cranbrook%' OR LOWER(p.address) LIKE '%goudhurst%'
        OR LOWER(p.address) LIKE '%me%' OR LOWER(p.address) LIKE '%tn%'
    )
    ORDER BY p.price ASC
    """,
).fetchall()

print(f"=== ALL FREEHOLD HOUSES (not flats) in wider TW/Maidstone/Snodland area: {len(rows)} ===\n")

for row in rows:
    (
        portal_id, address, price, property_type, tenure, bedrooms,
        size_sqft, council_tax_band, service_charge_pa, ground_rent_pa,
        title, is_favourite,
    ) = row

    asking_monthly = calculate_monthly(price, council_tax_band, service_charge_pa, ground_rent_pa)
    asking_tier = get_tier(asking_monthly)

    offer_price = round(price * (1 - OFFER_DISCOUNT))
    offer_monthly = calculate_monthly(offer_price, council_tax_band, service_charge_pa, ground_rent_pa)
    offer_tier = get_tier(offer_monthly)

    favourite_marker = " ***FAV" if is_favourite else ""
    size_display = f"{size_sqft:.0f}sqft" if size_sqft else "?sqft"
    beds_display = str(bedrooms) if bedrooms else "?"
    property_type_display = property_type or "?"
    council_tax_display = council_tax_band or "?"

    if offer_tier != asking_tier:
        tier_display = f"{asking_tier}->{offer_tier}"
    else:
        tier_display = asking_tier

    print(
        f"  {tier_display:>15s} | Ask {price:>7,} ({asking_monthly:,.0f}/mo)"
        f" -> Offer {offer_price:>7,} ({offer_monthly:,.0f}/mo)"
        f" | {size_display:>7s} | {beds_display}bed {property_type_display}"
        f" | {tenure} | CT:{council_tax_display}"
        f" | {address[:55]}{favourite_marker}"
    )
    print(f"                    https://www.rightmove.co.uk/properties/{portal_id}")

print()

# Summary
within_stretch_asking = sum(1 for r in rows if get_tier(calculate_monthly(r[2], r[7], r[8], r[9])) != "RED")
within_stretch_offer = sum(
    1 for r in rows
    if get_tier(calculate_monthly(round(r[2] * 0.93), r[7], r[8], r[9])) != "RED"
)
print(f"Within STRETCH at asking: {within_stretch_asking}")
print(f"Within STRETCH with 7% offer: {within_stretch_offer}")
print(f"Total freehold houses found: {len(rows)}")

conn.close()
