"""Properties that PASS both gates: >= 483 sqft AND <= £1,200/mo at 7% offer."""
import sqlite3

DEPOSIT = 37500
RATE = 0.045
TERM_MONTHS = 360
BILLS = 198
CT_BANDS = {"A": 91, "B": 109, "C": 127, "D": 145, "E": 163}
GREEN = 993
AMBER = 1072
STRETCH = 1200
MIN_SIZE = 483
OFFER_DISCOUNT = 0.07
RATE_MONTHLY = RATE / 12


def calculate_monthly(purchase_price, council_tax_band, service_charge_pa, ground_rent_pa):
    mortgage_amount = max(purchase_price - DEPOSIT, 0)
    if mortgage_amount > 0:
        monthly_mortgage = mortgage_amount * (
            RATE_MONTHLY * (1 + RATE_MONTHLY) ** TERM_MONTHS
        ) / ((1 + RATE_MONTHLY) ** TERM_MONTHS - 1)
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


conn = sqlite3.connect("data/property_search.db")
cursor = conn.cursor()
cursor.execute(
    """
    SELECT p.portal_id, p.address, p.price, p.property_type, p.tenure, p.bedrooms,
           p.size_sqft, p.council_tax_band, p.service_charge_pa, p.ground_rent_pa,
           CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END as is_fav
    FROM properties p
    LEFT JOIN favourites f ON f.property_id = p.id
    WHERE p.status = 'active' AND p.size_sqft >= ?
    ORDER BY p.size_sqft DESC
    """,
    (MIN_SIZE,),
)

passes = []
for row in cursor.fetchall():
    (portal_id, address, price, property_type, tenure, bedrooms,
     size_sqft, council_tax_band, service_charge_pa, ground_rent_pa, is_fav) = row

    asking_monthly = calculate_monthly(price, council_tax_band, service_charge_pa, ground_rent_pa)
    offer_price = round(price * (1 - OFFER_DISCOUNT))
    offer_monthly = calculate_monthly(offer_price, council_tax_band, service_charge_pa, ground_rent_pa)
    offer_tier = get_tier(offer_monthly)
    asking_tier = get_tier(asking_monthly)

    if offer_monthly <= STRETCH:
        passes.append({
            "portal_id": portal_id,
            "address": address,
            "price": price,
            "offer_price": offer_price,
            "type": property_type or "?",
            "tenure": (tenure or "?")[:18],
            "beds": bedrooms or "?",
            "size": size_sqft,
            "asking_monthly": asking_monthly,
            "asking_tier": asking_tier,
            "offer_monthly": offer_monthly,
            "offer_tier": offer_tier,
            "is_fav": is_fav,
            "service_charge": service_charge_pa or 0,
            "council_tax_band": council_tax_band or "?",
        })

passes.sort(key=lambda entry: entry["offer_monthly"])

print(f"=== PASS LIST: >= {MIN_SIZE} sqft AND <= £{STRETCH}/mo at 7% offer ===")
print(f"Total qualifying: {len(passes)}\n")

for index, entry in enumerate(passes, 1):
    favourite_marker = " ***FAV" if entry["is_fav"] else ""
    short_address = entry["address"][:55]
    beds_display = entry["beds"]
    tier_display = entry["offer_tier"]
    if entry["asking_tier"] != entry["offer_tier"]:
        tier_display = f"{entry['asking_tier']}→{entry['offer_tier']}"

    print(
        f"{index:>2}. {entry['size']:>4.0f}sqft | "
        f"Ask £{entry['price']:>7,} (£{entry['asking_monthly']:,.0f}/mo) → "
        f"Offer £{entry['offer_price']:>7,} (£{entry['offer_monthly']:,.0f}/mo) | "
        f"{tier_display} | "
        f"{beds_display}bed {entry['type']} | {entry['tenure']} | "
        f"SC:£{entry['service_charge']:,.0f}/yr | CT:{entry['council_tax_band']}"
        f"{favourite_marker}"
    )
    print(f"    https://www.rightmove.co.uk/properties/{entry['portal_id']}")

conn.close()
