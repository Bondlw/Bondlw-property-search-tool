"""Wipe old favourites and add the 4 new shortlisted properties."""
import sqlite3

DEPOSIT = 37500
RATE = 0.045
TERM = 360
BILLS = 198
OFFER = 0.07
CT_LOOKUP = {"A": 91, "B": 109, "C": 127, "D": 145, "E": 163}
MONTHLY_RATE = RATE / 12


def calculate_mortgage(principal):
    if principal <= 0:
        return 0
    return principal * (MONTHLY_RATE * (1 + MONTHLY_RATE) ** TERM) / (
        (1 + MONTHLY_RATE) ** TERM - 1
    )


def get_tier(total):
    if total <= 993:
        return "GREEN"
    elif total <= 1072:
        return "AMBER"
    elif total <= 1200:
        return "STRETCH"
    return "RED"


def main():
    conn = sqlite3.connect("data/property_search.db")
    cursor = conn.cursor()

    # Show current favourites before wiping
    cursor.execute(
        "SELECT p.address, p.portal_id FROM properties p "
        "JOIN favourites f ON f.property_id = p.id"
    )
    old_favs = cursor.fetchall()
    print(f"WIPING {len(old_favs)} OLD FAVOURITES:")
    for address, portal_id in old_favs:
        print(f"  - {address[:60]} ({portal_id})")

    # Wipe favourites
    cursor.execute("DELETE FROM favourites")
    print(f"\nDeleted {cursor.rowcount} favourites.")

    # New favourites - the 4 shortlisted
    new_portal_ids = [87629463, 170883641, 172756211, 163721603]

    for portal_id in new_portal_ids:
        cursor.execute(
            "SELECT id FROM properties WHERE portal_id = ?", (portal_id,)
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "INSERT INTO favourites (property_id) VALUES (?)", (row[0],)
            )
            print(f"Added favourite: portal_id={portal_id}")
        else:
            print(f"NOT FOUND: portal_id={portal_id}")

    conn.commit()

    # Full breakdown for each
    print("\n" + "=" * 100)
    print("NEW FAVOURITES - FULL ALL-IN COST BREAKDOWN")
    print("=" * 100)

    for portal_id in new_portal_ids:
        cursor.execute(
            """SELECT p.portal_id, p.address, p.price, p.property_type, p.tenure,
                p.bedrooms, p.size_sqft, p.council_tax_band,
                p.service_charge_pa, p.ground_rent_pa
            FROM properties p WHERE p.portal_id = ?""",
            (portal_id,),
        )
        row = cursor.fetchone()
        if not row:
            continue
        (
            _pid, address, price, prop_type, tenure, bedrooms,
            size_sqft, council_tax_band, service_charge, ground_rent,
        ) = row
        service_charge = service_charge or 0
        ground_rent = ground_rent or 0
        council_tax_monthly = CT_LOOKUP.get(council_tax_band, 127)

        # Asking price calcs
        asking_mortgage = calculate_mortgage(max(price - DEPOSIT, 0))
        service_charge_monthly = service_charge / 12
        ground_rent_monthly = ground_rent / 12
        asking_total = (
            asking_mortgage + BILLS + council_tax_monthly
            + service_charge_monthly + ground_rent_monthly
        )

        # Offer price calcs
        offer_price = round(price * (1 - OFFER))
        offer_mortgage = calculate_mortgage(max(offer_price - DEPOSIT, 0))
        offer_total = (
            offer_mortgage + BILLS + council_tax_monthly
            + service_charge_monthly + ground_rent_monthly
        )

        print(f"\n--- {address} ---")
        print(
            f"Type: {bedrooms}bed {prop_type} | Tenure: {tenure} "
            f"| Size: {size_sqft:.0f}sqft | CT Band: {council_tax_band}"
        )
        print(f"https://www.rightmove.co.uk/properties/{portal_id}")
        print()
        print(f"  ASKING PRICE: GBP{price:,}")
        print(
            f"    Mortgage (GBP{price - DEPOSIT:,} @ 4.5%/30yr): "
            f"GBP{asking_mortgage:,.0f}/mo"
        )
        print(f"    Bills (fixed):                          GBP{BILLS}/mo")
        print(
            f"    Council Tax (Band {council_tax_band or '?'}):              "
            f"GBP{council_tax_monthly}/mo"
        )
        print(
            f"    Service Charge (GBP{service_charge:,.0f}/yr):            "
            f"GBP{service_charge_monthly:,.0f}/mo"
        )
        print(
            f"    Ground Rent (GBP{ground_rent:,.0f}/yr):               "
            f"GBP{ground_rent_monthly:,.0f}/mo"
        )
        print(f"    ----------------------------------------")
        print(
            f"    TOTAL:                                  "
            f"GBP{asking_total:,.0f}/mo  [{get_tier(asking_total)}]"
        )
        print()
        print(f"  7% OFFER: GBP{offer_price:,} (save GBP{price - offer_price:,})")
        print(
            f"    Mortgage (GBP{offer_price - DEPOSIT:,} @ 4.5%/30yr): "
            f"GBP{offer_mortgage:,.0f}/mo"
        )
        print(
            f"    Bills + CT + SC + GR:                   "
            f"GBP{BILLS + council_tax_monthly + service_charge_monthly + ground_rent_monthly:,.0f}/mo"
        )
        print(f"    ----------------------------------------")
        print(
            f"    TOTAL:                                  "
            f"GBP{offer_total:,.0f}/mo  [{get_tier(offer_total)}]"
        )
        print(
            f"    Saving vs asking: GBP{asking_total - offer_total:,.0f}/mo"
        )

    # Summary table
    print("\n" + "=" * 100)
    print("SUMMARY COMPARISON")
    print("=" * 100)
    header = (
        f"{'Property':<30} {'Sqft':>5} {'Ask':>10} {'Ask/mo':>8} "
        f"{'Offer':>10} {'Offer/mo':>8} {'Tier':>8}"
    )
    print(header)
    print("-" * 85)
    for portal_id in new_portal_ids:
        cursor.execute(
            "SELECT address, price, size_sqft, council_tax_band, "
            "service_charge_pa, ground_rent_pa "
            "FROM properties WHERE portal_id = ?",
            (portal_id,),
        )
        row = cursor.fetchone()
        address, price, size_sqft, ctb, svc_charge, gnd_rent = row
        svc_charge = svc_charge or 0
        gnd_rent = gnd_rent or 0
        ct_monthly = CT_LOOKUP.get(ctb, 127)
        asking_total = (
            calculate_mortgage(max(price - DEPOSIT, 0))
            + BILLS + ct_monthly + svc_charge / 12 + gnd_rent / 12
        )
        offer_price = round(price * (1 - OFFER))
        offer_total = (
            calculate_mortgage(max(offer_price - DEPOSIT, 0))
            + BILLS + ct_monthly + svc_charge / 12 + gnd_rent / 12
        )
        short_address = address.split(",")[0].strip()
        print(
            f"{short_address:<30} {size_sqft:>5.0f} "
            f"GBP{price:>8,} GBP{asking_total:>5,.0f} "
            f"GBP{offer_price:>8,} GBP{offer_total:>5,.0f} "
            f"{get_tier(offer_total):>8}"
        )

    conn.close()


if __name__ == "__main__":
    main()
