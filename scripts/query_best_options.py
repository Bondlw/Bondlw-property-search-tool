"""Query best options >= 483 sqft in TW/Maidstone/Snodland/Tonbridge area."""
import sqlite3

DEPOSIT = 37500
RATE = 0.045
TERM_MONTHS = 30 * 12
BILLS = 198
CT_BANDS = {"A": 91, "B": 109, "C": 127, "D": 145, "E": 163}
GREEN = 993
AMBER = 1072
STRETCH = 1200
MIN_SIZE = 483  # Springview — felt decent
OFFER_DISCOUNT = 0.07  # 7% below asking

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

conn = sqlite3.connect("data/property_search.db")
cursor = conn.cursor()

cursor.execute(
    """
    SELECT p.portal_id, p.address, p.price, p.property_type, p.tenure, p.bedrooms,
           p.size_sqft, p.council_tax_band, p.service_charge_pa, p.ground_rent_pa,
           p.title,
           CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END as is_fav
    FROM properties p
    LEFT JOIN favourites f ON f.property_id = p.id
    WHERE p.status = 'active'
    AND p.size_sqft >= ?
    AND (
        LOWER(p.address) LIKE '%tunbridge wells%' OR LOWER(p.address) LIKE '%maidstone%'
        OR LOWER(p.address) LIKE '%snodland%' OR LOWER(p.address) LIKE '%tonbridge%'
        OR LOWER(p.address) LIKE '%royal tunbridge%'
    )
    ORDER BY p.size_sqft DESC
    """,
    (MIN_SIZE,),
)

rows = cursor.fetchall()
print(f"Properties >= {MIN_SIZE} sqft in TW/Maidstone/Snodland/Tonbridge: {len(rows)}\n")

freeholds = []
leaseholds = []

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

    entry = {
        "portal_id": portal_id,
        "address": address,
        "price": price,
        "offer_price": offer_price,
        "type": property_type or "?",
        "tenure": tenure or "?",
        "beds": bedrooms or "?",
        "size": size_sqft,
        "asking_monthly": asking_monthly,
        "asking_tier": asking_tier,
        "offer_monthly": offer_monthly,
        "offer_tier": offer_tier,
        "is_fav": is_favourite,
        "service_charge": service_charge_pa or 0,
        "council_tax_band": council_tax_band or "?",
    }

    is_freehold = tenure and "freehold" in tenure.lower()
    is_flat = property_type and "flat" in property_type.lower()

    if is_freehold and not is_flat:
        freeholds.append(entry)
    else:
        leaseholds.append(entry)

freeholds.sort(key=lambda entry: entry["offer_monthly"])
leaseholds.sort(key=lambda entry: entry["offer_monthly"])


def print_entry(entry):
    favourite_marker = " ***FAV" if entry["is_fav"] else ""
    short_address = entry["address"][:50]
    # Show tier change if offer improves it
    if entry["offer_tier"] != entry["asking_tier"]:
        tier_display = f"{entry['asking_tier']:>7s}→{entry['offer_tier']}"
    else:
        tier_display = f"{entry['asking_tier']:>7s}       "
    print(
        f"  {tier_display} | Ask £{entry['price']:>7,.0f} (£{entry['asking_monthly']:,.0f}/mo)"
        f" → Offer £{entry['offer_price']:>7,.0f} (£{entry['offer_monthly']:,.0f}/mo)"
        f" | {entry['size']:,.0f}sqft | {entry['beds']}bed {entry['type']}"
        f" | {entry['tenure']} | SC:£{entry['service_charge']:,.0f}/yr"
        f" | {short_address}{favourite_marker}"
    )
    print(f"          https://www.rightmove.co.uk/properties/{entry['portal_id']}")


print("=" * 130)
print("FREEHOLD HOUSES (not flats) >= 483 sqft")
print("=" * 130)
if not freeholds:
    print("  None found with size data in these areas")
else:
    for entry in freeholds:
        print_entry(entry)
    print()

print("=" * 130)
print(f"FLATS >= {MIN_SIZE} sqft — AFFORDABLE at asking OR with 7% offer (within STRETCH = £1,200/mo)")
print("=" * 130)

# Show properties that are affordable at either asking or offer price
affordable_leasehold = [entry for entry in leaseholds if entry["offer_tier"] != "RED"]
over_budget_leasehold = [entry for entry in leaseholds if entry["offer_tier"] == "RED"]

if not affordable_leasehold:
    print("  None found")
else:
    for entry in affordable_leasehold:
        print_entry(entry)

if over_budget_leasehold:
    print(f"\n  ... plus {len(over_budget_leasehold)} still RED even with 7% offer:")
    for entry in over_budget_leasehold:
        print_entry(entry)

# Springview comparison
print()
print("=" * 110)
print("SPRINGVIEW REFERENCE: 483 sqft, Springview Close, Tunbridge Wells — felt 'decent size'")
print("=" * 110)

conn.close()
