"""Hard gate checks for property qualification.

ALL gates must pass for a property to qualify.
Any unknown/TBC field = automatic REJECT.
"""

import json
import re
from dataclasses import dataclass


@dataclass
class GateResult:
    gate_name: str
    passed: bool
    reason: str
    needs_verification: bool = False


def check_all_gates(
    property_data: dict, enrichment: dict | None, config: dict
) -> tuple[bool, list[GateResult]]:
    """Run all hard gates. Returns (all_passed, list_of_results)."""
    gates = [
        check_price_cap,
        check_monthly_cost,
        check_min_bedrooms,
        check_separate_lounge,
        check_move_in_ready,
        check_not_retirement,
        check_not_auction,
        check_not_non_standard,
        check_lease_length,
        check_service_charge,
        check_ground_rent,
        check_no_doubling_clause,
        check_no_tbc_fields,
        check_council_tax_band,
        check_epc_rating,
    ]

    # Enrichment-dependent gates (only run if enrichment data exists)
    if enrichment:
        gates.extend([
            check_station_walkable,
            check_supermarket_walkable,
            check_crime_safety,
            check_flood_risk,
        ])

    results = [gate(property_data, enrichment, config) for gate in gates]
    all_passed = all(r.passed for r in results)
    return all_passed, results


def _get_description_lower(prop: dict) -> str:
    """Get combined lowercase description and key features text."""
    desc = (prop.get("description") or "").lower()
    kf = prop.get("key_features", "")
    if isinstance(kf, str):
        try:
            kf = json.loads(kf)
        except (json.JSONDecodeError, TypeError):
            kf = [kf] if kf else []
    if isinstance(kf, list):
        kf = " ".join(str(f) for f in kf).lower()
    else:
        kf = str(kf).lower()
    return f"{desc} {kf}"


def _get_tenure(prop: dict) -> str | None:
    tenure = prop.get("tenure")
    return tenure.lower() if tenure else None


def _estimate_monthly_housing(prop: dict, config: dict) -> float | None:
    """Estimate total monthly housing cost (mortgage + SC + GR + CT).

    Returns None if price is missing.
    """
    from ..utils.financial_calculator import FinancialCalculator
    calc = FinancialCalculator(config)
    costs = calc.calculate_total_monthly(prop)
    return costs["total_monthly"]


def check_price_cap(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Check price is within budget caps (tenure-specific).

    Between responsible_max and absolute_max, also checks that total monthly
    housing cost stays within the AMBER threshold (monthly_target.max).
    """
    price = prop.get("price", 0)
    tenure = _get_tenure(prop)
    budget = config.get("budget", {})
    monthly_max = config.get("monthly_target", {}).get("max", 928)

    # Check minimum price across all tenures
    min_prices = [
        budget.get("freehold", {}).get("ideal_min", 0),
        budget.get("leasehold", {}).get("ideal_min", 0),
    ]
    price_floor = min(p for p in min_prices if p > 0) if any(p > 0 for p in min_prices) else 0
    if price_floor and price < price_floor:
        return GateResult("price_cap", False, f"£{price:,} below minimum £{price_floor:,}")

    if not tenure:
        return GateResult("price_cap", False, "Tenure unknown — cannot determine budget cap")

    if tenure == "freehold":
        caps = budget.get("freehold", {})
        responsible_max = caps.get("responsible_max", 190000)
        absolute_max = caps.get("absolute_max", 200000)

        if price > absolute_max:
            return GateResult("price_cap", False, f"£{price:,} exceeds freehold cap £{absolute_max:,}")

        # Between responsible and absolute: check monthly cost
        if price > responsible_max:
            monthly = _estimate_monthly_housing(prop, config)
            if monthly and monthly > monthly_max:
                return GateResult(
                    "price_cap", False,
                    f"£{price:,} above £{responsible_max:,} and £{monthly:,.0f}/mo > £{monthly_max}/mo target"
                )

        return GateResult("price_cap", True, f"£{price:,} within freehold cap £{absolute_max:,}")

    if tenure in ("leasehold", "share_of_freehold"):
        caps = budget.get("leasehold", {})
        responsible_max = caps.get("responsible_max", 170000)
        absolute_max = caps.get("absolute_max", 180000)
        sc_cap = caps.get("service_charge_cap_for_absolute_max", 900)

        if price > absolute_max:
            return GateResult("price_cap", False, f"£{price:,} exceeds leasehold cap £{absolute_max:,}")

        sc = prop.get("service_charge_pa")
        if price > responsible_max:
            if sc is None:
                return GateResult(
                    "price_cap", False,
                    f"£{price:,} above £{responsible_max:,} but SC unknown"
                )
            if sc >= sc_cap:
                return GateResult(
                    "price_cap", False,
                    f"£{price:,} above £{responsible_max:,} requires SC < £{sc_cap}, but SC is £{sc}"
                )
            # Also check monthly cost
            monthly = _estimate_monthly_housing(prop, config)
            if monthly and monthly > monthly_max:
                return GateResult(
                    "price_cap", False,
                    f"£{price:,} above £{responsible_max:,} and £{monthly:,.0f}/mo > £{monthly_max}/mo target"
                )

        return GateResult("price_cap", True, f"£{price:,} within leasehold budget")

    return GateResult("price_cap", False, f"Unknown tenure: {tenure}")


def check_monthly_cost(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Check total monthly housing cost is within qualifying ceiling.

    This is the definitive affordability gate — even if a property's price
    is below the cap, high service charges, ground rent, or council tax
    can push the monthly cost above the acceptance criteria.
    Qualifying ceiling = monthly_target.max (£889 housing = £1,100 all-in).
    Properties under monthly_target.min (£795) show as GREEN (comfortable).
    Properties between min and max show as AMBER (qualifying stretch).
    """
    monthly_max = config.get("monthly_target", {}).get("max", 889)
    monthly = _estimate_monthly_housing(prop, config)
    if monthly is None:
        return GateResult("monthly_cost", False, "Cannot estimate monthly cost")
    if monthly > monthly_max:
        return GateResult(
            "monthly_cost", False,
            f"Housing £{monthly:,.0f}/mo exceeds £{monthly_max}/mo qualifying ceiling"
        )
    return GateResult("monthly_cost", True, f"Housing £{monthly:,.0f}/mo within £{monthly_max}/mo qualifying ceiling")


def check_min_bedrooms(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Check minimum bedroom count."""
    min_beds = config.get("hard_gates", {}).get("min_bedrooms", 1)
    bedrooms = prop.get("bedrooms")

    if bedrooms is None:
        return GateResult("min_bedrooms", False, "Bedroom count unknown")
    if bedrooms < min_beds:
        return GateResult("min_bedrooms", False, f"{bedrooms} bedrooms < minimum {min_beds}")
    return GateResult("min_bedrooms", True, f"{bedrooms} bedrooms")


def check_separate_lounge(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Reject studios and bedsits only."""
    text = _get_description_lower(prop)
    prop_type = (prop.get("property_type") or "").lower()

    # Reject studio
    if "studio" in prop_type or "studio" in text:
        if "recording studio" not in text and "studio flat" not in text.replace("studio", "", 1):
            return GateResult("separate_lounge", False, "Studio property")

    # Reject bedsit
    if "bedsit" in text:
        return GateResult("separate_lounge", False, "Bedsit")

    return GateResult("separate_lounge", True, "Not a studio or bedsit")



def check_move_in_ready(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Reject renovation projects and cash-only listings.

    "Investor" alone is NOT a rejection reason — agents routinely write
    "suitable for investors or owner-occupiers". Only explicit cash-only
    phrases (cash buyers only, cash only, etc.) trigger rejection.
    """
    text = _get_description_lower(prop)
    reject_terms = config.get("keywords", {}).get("reject_terms", [])

    # Check renovation/project reject terms from config
    project_keywords = [
        "modernisation", "updating", "renovation", "development", "building plot",
    ]
    renovation_terms = [
        t for t in reject_terms
        if any(w in t for w in project_keywords)
    ]
    for term in renovation_terms:
        if term.lower() in text:
            return GateResult("move_in_ready", False, f"Found reject term: '{term}'")

    # Cash-only check — "investor" or "first time buyer" alone are NOT rejection reasons
    cash_only_phrases = [
        "cash buyers only",
        "cash only",
        "cash purchase only",
        "cash offers only",
        "cash purchasers only",
    ]
    for phrase in cash_only_phrases:
        if phrase in text:
            return GateResult("move_in_ready", False, f"Cash-only listing: '{phrase}'")

    return GateResult("move_in_ready", True, "Move-in ready")


def check_not_non_standard(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Reject non-standard dwelling types: houseboats, caravans, park homes."""
    prop_type = (prop.get("property_type") or "").lower()
    title = (prop.get("title") or "").lower()
    # Only check start of description — avoids "near the boat yard" false positives
    desc_start = (prop.get("description") or "")[:300].lower()
    combined = f"{prop_type} {title} {desc_start}"

    non_standard_terms = [
        "houseboat", "house boat",
        "static caravan", "residential caravan",
        "mobile home",
        "park home",
        "static home",
    ]
    for term in non_standard_terms:
        if term in combined:
            return GateResult("not_non_standard", False, f"Non-standard dwelling: '{term}'")

    return GateResult("not_non_standard", True, "Standard property type")


def check_not_retirement(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Reject retirement/sheltered housing."""
    text = _get_description_lower(prop)
    retirement_terms = ["retirement", "over 55", "55+", "sheltered", "assisted living"]

    for term in retirement_terms:
        if term in text:
            return GateResult("not_retirement", False, f"Retirement property: '{term}'")

    return GateResult("not_retirement", True, "Not retirement")


def check_not_auction(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Reject auction listings.

    "Guide price" is normal estate agent terminology and does NOT indicate auction.
    Only reject when "auction" appears with contextual indicators.
    """
    text = _get_description_lower(prop)
    status = (prop.get("status") or "").lower()

    if "auction" in status:
        return GateResult("not_auction", False, "Auction listing (status)")

    # Skip if text says "not at auction" or "no longer at auction"
    cleaned = text.replace("not at auction", "").replace("no longer at auction", "")
    if "auction" in cleaned:
        # Confirm with contextual terms — avoid false positives
        auction_context = [
            "auction date", "lot number", "lot ", "offered at auction",
            "auction house", "sold at auction", "going to auction",
            "bidding", "auction on", "auction room",
        ]
        if any(term in text for term in auction_context):
            return GateResult("not_auction", False, "Auction property (contextual match)")
        # "auction" alone in description — still reject but with note
        return GateResult("not_auction", False, "Auction mentioned in description")

    return GateResult("not_auction", True, "Not auction")


def check_lease_length(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Check lease length for leasehold properties.

    Share of freehold has a lower minimum because extending is cheap
    (~£1k admin/legal) since you collectively own the freehold.
    Pure leasehold requires 120yr+ to stay well above the 80yr
    marriage value cliff where extension costs skyrocket.
    """
    tenure = _get_tenure(prop)

    if tenure == "freehold":
        return GateResult("lease_length", True, "Freehold — no lease")

    if tenure == "share_of_freehold":
        min_years = config.get("hard_gates", {}).get("sof_lease_minimum_years", 80)
        lease_years = prop.get("lease_years")

        if lease_years is None:
            return GateResult("lease_length", True, "SOF lease length unknown — needs verification", needs_verification=True)
        if lease_years < min_years:
            return GateResult("lease_length", False, f"SOF lease {lease_years}yr < minimum {min_years}yr")
        return GateResult("lease_length", True, f"SOF lease {lease_years}yr (extension ~£1k)")

    if tenure == "leasehold":
        min_years = config.get("hard_gates", {}).get("lease_minimum_years", 120)
        lease_years = prop.get("lease_years")

        if lease_years is None:
            return GateResult("lease_length", True, "Lease length unknown — needs verification", needs_verification=True)
        if lease_years < min_years:
            return GateResult("lease_length", False, f"Lease {lease_years}yr < minimum {min_years}yr")
        return GateResult("lease_length", True, f"Lease {lease_years}yr")

    return GateResult("lease_length", False, f"Unknown tenure: {tenure}")


def check_service_charge(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Check service charge for leasehold properties."""
    tenure = _get_tenure(prop)

    if tenure == "freehold":
        return GateResult("service_charge", True, "Freehold — no service charge")

    if tenure in ("leasehold", "share_of_freehold"):
        max_sc = config.get("hard_gates", {}).get("service_charge_max_pa", 1200)
        sc = prop.get("service_charge_pa")

        if sc is None:
            return GateResult("service_charge", True, "Service charge unknown — needs verification", needs_verification=True)
        if sc > max_sc:
            return GateResult("service_charge", False, f"SC £{sc}/yr exceeds cap £{max_sc}/yr")
        return GateResult("service_charge", True, f"SC £{sc}/yr within cap £{max_sc}/yr")

    return GateResult("service_charge", False, f"Unknown tenure: {tenure}")


def check_ground_rent(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Check ground rent for leasehold properties."""
    tenure = _get_tenure(prop)

    if tenure == "freehold":
        return GateResult("ground_rent", True, "Freehold — no ground rent")

    if tenure in ("leasehold", "share_of_freehold"):
        max_gr = config.get("hard_gates", {}).get("ground_rent_max_pa", 250)
        gr = prop.get("ground_rent_pa")

        if gr is None:
            return GateResult("ground_rent", True, "Ground rent unknown — needs verification", needs_verification=True)
        if gr > max_gr:
            return GateResult("ground_rent", False, f"GR £{gr}/yr exceeds cap £{max_gr}/yr")
        return GateResult("ground_rent", True, f"GR £{gr}/yr within cap £{max_gr}/yr")

    return GateResult("ground_rent", False, f"Unknown tenure: {tenure}")


def check_no_doubling_clause(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Reject properties with ground rent doubling clauses."""
    tenure = _get_tenure(prop)
    if tenure == "freehold":
        return GateResult("no_doubling_clause", True, "Freehold — N/A")

    text = _get_description_lower(prop)
    doubling_terms = config.get("keywords", {}).get("doubling_clause_terms", [])

    for term in doubling_terms:
        if term.lower() in text:
            return GateResult("no_doubling_clause", False, f"Doubling clause indicator: '{term}'")

    return GateResult("no_doubling_clause", True, "No doubling clause detected")


def check_no_tbc_fields(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Flag if critical leasehold fields are TBC/unknown — needs verification."""
    tenure = _get_tenure(prop)
    if tenure == "freehold":
        return GateResult("no_tbc_fields", True, "Freehold — N/A")

    if tenure not in ("leasehold", "share_of_freehold"):
        return GateResult("no_tbc_fields", True, "Tenure unknown — needs verification", needs_verification=True)

    text = _get_description_lower(prop)
    tbc_phrases = ["tbc", "to be confirmed", "ask agent", "awaiting details", "contact agent"]

    # Check description for TBC mentions near key terms
    for phrase in tbc_phrases:
        if phrase in text:
            # Only flag if near relevant terms
            for field in ["service charge", "ground rent", "lease", "council tax"]:
                # Check if TBC phrase is within 50 chars of the field mention
                for match in re.finditer(re.escape(phrase), text):
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    context = text[start:end]
                    if field in context:
                        return GateResult(
                            "no_tbc_fields", True,
                            f"'{phrase}' found near '{field}' — needs verification",
                            needs_verification=True,
                        )

    return GateResult("no_tbc_fields", True, "No TBC fields detected")


def check_council_tax_band(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Check council tax band.

    If band is KNOWN and exceeds the limit, reject.
    If band is UNKNOWN, pass with a 'needs verification' note — since
    Rightmove rarely publishes CT band, requiring it would reject everything.
    The report highlights properties with unverified CT band.
    """
    max_band = config.get("hard_gates", {}).get("council_tax_max_band", "C")
    band = prop.get("council_tax_band")

    # Also check enrichment data
    if not band and enrichment:
        band = enrichment.get("council_tax_band_verified")

    if not band:
        return GateResult("council_tax_band", True, "Council tax band unverified — needs checking")

    band = band.upper().strip()
    allowed = [chr(i) for i in range(ord("A"), ord(max_band) + 1)]

    if band in allowed:
        return GateResult("council_tax_band", True, f"Council tax Band {band}")
    return GateResult("council_tax_band", False, f"Council tax Band {band} exceeds max Band {max_band}")


def check_epc_rating(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Check EPC energy efficiency rating.

    If rating is KNOWN and below the minimum, reject.
    If rating is UNKNOWN, pass with a 'needs checking' note — since
    Rightmove rarely publishes EPC, requiring it would reject everything.
    """
    min_epc = config.get("hard_gates", {}).get("epc_minimum_rating", "C")
    epc = prop.get("epc_rating")

    if not epc:
        return GateResult("epc_rating", True, "EPC rating unknown \u2014 needs checking")

    epc = epc.upper().strip()
    allowed = [chr(i) for i in range(ord("A"), ord(min_epc) + 1)]

    if epc in allowed:
        return GateResult("epc_rating", True, f"EPC {epc}")
    return GateResult("epc_rating", False, f"EPC {epc} below minimum {min_epc}")


# --- Enrichment-dependent gates ---

def check_station_walkable(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Check distance to nearest train station."""
    if not enrichment:
        return GateResult("station_walkable", False, "No enrichment data")

    max_min = config.get("hard_gates", {}).get("station_max_walk_min", 25)
    walk_min = enrichment.get("nearest_station_walk_min")

    if walk_min is None:
        return GateResult("station_walkable", False, "Station distance unknown")
    if walk_min > max_min:
        station = enrichment.get("nearest_station_name", "Unknown")
        return GateResult(
            "station_walkable", False,
            f"{station}: {walk_min} min walk > {max_min} min max"
        )
    station = enrichment.get("nearest_station_name", "Unknown")
    return GateResult("station_walkable", True, f"{station}: {walk_min} min walk")


def check_supermarket_walkable(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Check distance to nearest major supermarket (any chain)."""
    if not enrichment:
        return GateResult("supermarket_walkable", False, "No enrichment data")

    max_min = config.get("hard_gates", {}).get("supermarket_max_walk_min", 25)

    # Prefer nearest_supermarket_* (any chain, added in v3 enrichment)
    best = enrichment.get("nearest_supermarket_walk_min")
    best_name = enrichment.get("nearest_supermarket_name", "Supermarket")

    # Fall back to Lidl/Aldi for properties enriched before v3
    if best is None:
        lidl_min = enrichment.get("nearest_lidl_walk_min")
        aldi_min = enrichment.get("nearest_aldi_walk_min")
        if lidl_min is not None:
            best = lidl_min
            best_name = "Lidl"
        if aldi_min is not None and (best is None or aldi_min < best):
            best = aldi_min
            best_name = "Aldi"

    if best is None:
        return GateResult("supermarket_walkable", False, "No supermarket found nearby")
    if best > max_min:
        return GateResult(
            "supermarket_walkable", False,
            f"Nearest {best_name}: {best} min walk > {max_min} min max"
        )
    return GateResult("supermarket_walkable", True, f"Nearest {best_name}: {best} min walk")


def check_crime_safety(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Check crime statistics for the area."""
    if not enrichment:
        return GateResult("crime_safety", False, "No enrichment data")

    crime_summary = enrichment.get("crime_summary")
    if not crime_summary:
        return GateResult("crime_safety", False, "No crime data")

    if isinstance(crime_summary, str):
        try:
            crime_summary = json.loads(crime_summary)
        except json.JSONDecodeError:
            return GateResult("crime_safety", False, "Invalid crime data")

    thresholds = config.get("crime_thresholds", {})
    failures = []

    checks = {
        "asb": thresholds.get("asb_monthly_max", 15),
        "burglary": thresholds.get("burglary_monthly_max", 5),
        "drugs": thresholds.get("drugs_monthly_max", 5),
        "violent": thresholds.get("violent_monthly_max", 10),
    }

    for category, max_val in checks.items():
        actual = crime_summary.get(category, 0)
        if actual > max_val:
            failures.append(f"{category}: {actual}/mo > {max_val}")

    if failures:
        return GateResult("crime_safety", False, f"High crime: {', '.join(failures)}")
    return GateResult("crime_safety", True, "Crime levels within thresholds")


def check_flood_risk(prop: dict, enrichment: dict | None, config: dict) -> GateResult:
    """Check flood risk zone."""
    if not enrichment:
        return GateResult("flood_risk", False, "No enrichment data")

    reject_zone = config.get("hard_gates", {}).get("flood_zone_reject", 3)
    flood_zone = enrichment.get("flood_zone")

    if flood_zone is None:
        # Don't reject if flood data unavailable — it's supplementary
        return GateResult("flood_risk", True, "Flood zone data not available")
    if flood_zone >= reject_zone:
        return GateResult("flood_risk", False, f"Flood Zone {flood_zone} (reject threshold: {reject_zone})")
    return GateResult("flood_risk", True, f"Flood Zone {flood_zone}")
