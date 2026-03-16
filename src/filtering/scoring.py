"""100-point scoring engine for qualifying properties.

Only runs on properties that have passed ALL hard gates.
Each score component returns a reason string explaining the score.
"""

import json


def score_property(
    property_data: dict, enrichment: dict | None, config: dict
) -> dict:
    """Score a qualifying property. Returns breakdown, reasons and total."""
    weights = config.get("scoring", {})

    ff, ff_reason = score_financial_fit(property_data, config, weights.get("financial_fit", 30))
    cs, cs_reason = score_crime_safety(enrichment, weights.get("crime_safety", 25))
    cp, cp_reason = score_cost_predictability(property_data, weights.get("cost_predictability", 15))
    ll, ll_reason = score_layout_livability(property_data, weights.get("layout_livability", 15))
    wk, wk_reason = score_walkability(enrichment, config, weights.get("walkability", 10))
    lt, lt_reason = score_long_term_flexibility(property_data, enrichment, weights.get("long_term_flexibility", 5))

    total = round(ff + cs + cp + ll + wk + lt, 1)

    return {
        "financial_fit": ff,
        "financial_fit_reason": ff_reason,
        "crime_safety": cs,
        "crime_safety_reason": cs_reason,
        "cost_predictability": cp,
        "cost_predictability_reason": cp_reason,
        "layout_livability": ll,
        "layout_livability_reason": ll_reason,
        "walkability": wk,
        "walkability_reason": wk_reason,
        "long_term_flexibility": lt,
        "long_term_flexibility_reason": lt_reason,
        "total": total,
    }


def score_financial_fit(prop: dict, config: dict, max_points: float) -> tuple[float, str]:
    """Score based on total all-in monthly cost (housing + bills) vs target range.

    Full marks when all-in is under (target_min + bills). Linearly decreasing to (target_max + bills).
    """
    from ..utils.financial_calculator import FinancialCalculator
    calc = FinancialCalculator(config)
    costs = calc.calculate_full_monthly_cost(prop)
    total = costs["total_all_in_monthly"]

    bills = config.get("estimated_bills", {}).get("total_monthly", 211)
    target_min = config.get("monthly_target", {}).get("min", 795) + bills
    target_max = config.get("monthly_target", {}).get("max", 928) + bills
    take_home = config.get("user", {}).get("monthly_take_home", 2650)

    if total <= 0:
        return max_points * 0.5, "Monthly cost unavailable — partial score"

    pct = round(total / take_home * 100, 1) if take_home else 0

    if total < target_min:
        return max_points, f"All-in £{total:,.0f}/mo ({pct}% of take-home) — under target (Green)"

    if total <= target_max:
        ratio = (total - target_min) / (target_max - target_min)
        score = round(max_points * (1.0 - 0.4 * ratio), 1)
        return score, f"All-in £{total:,.0f}/mo ({pct}% of take-home) — within target (Amber)"

    over_pct = (total - target_max) / target_max
    penalty = min(over_pct * 5, 1.0)
    score = round(max(0, max_points * 0.4 * (1 - penalty)), 1)
    return score, f"All-in £{total:,.0f}/mo ({pct}% of take-home) — over target (Red)"


def score_crime_safety(enrichment: dict | None, max_points: float) -> tuple[float, str]:
    """Score based on crime statistics. Lower crime = higher score."""
    if not enrichment:
        return max_points * 0.5, "No crime data — partial score"

    crime_summary = enrichment.get("crime_summary")
    if not crime_summary:
        return max_points * 0.5, "No crime data — partial score"

    if isinstance(crime_summary, str):
        try:
            crime_summary = json.loads(crime_summary)
        except json.JSONDecodeError:
            return max_points * 0.5, "Invalid crime data — partial score"

    category_weights = {
        "violent": 0.32,
        "asb": 0.20,
        "burglary": 0.20,
        "drugs": 0.16,
        "other": 0.12,
    }
    good_thresholds = {"violent": 5, "asb": 8, "burglary": 2, "drugs": 2, "other": 5}

    total_score = 0.0
    parts = []
    for category, weight in category_weights.items():
        actual = crime_summary.get(category, 0)
        threshold = good_thresholds.get(category, 5)
        if actual <= threshold:
            ratio = 1.0
        else:
            ratio = max(0, 1.0 - (actual - threshold) / (threshold * 2))
        total_score += weight * ratio
        if actual > 0:
            parts.append(f"{category} {actual}/mo")

    score = round(max_points * total_score, 1)
    total_crimes = crime_summary.get("total", sum(
        crime_summary.get(c, 0) for c in ["violent", "asb", "burglary", "drugs", "other"]
    ))
    summary = f"Total {total_crimes}/mo" + (f" ({', '.join(parts[:3])})" if parts else "")
    return score, summary


def score_cost_predictability(prop: dict, max_points: float) -> tuple[float, str]:
    """Score based on how predictable ongoing costs are."""
    tenure = (prop.get("tenure") or "").lower()

    if tenure == "freehold":
        return max_points, "Freehold — no SC/GR exposure, fully predictable"

    if tenure not in ("leasehold", "share_of_freehold"):
        return max_points * 0.3, "Tenure unknown — partial score"

    score = 0.0
    parts = []

    lease = prop.get("lease_years")
    if lease:
        if lease >= 900:
            score += 0.4; parts.append(f"{lease}yr lease (excellent)")
        elif lease >= 200:
            score += 0.35; parts.append(f"{lease}yr lease (very good)")
        elif lease >= 150:
            score += 0.3; parts.append(f"{lease}yr lease (good)")
        elif lease >= 120:
            score += 0.2; parts.append(f"{lease}yr lease (acceptable)")
        else:
            score += 0.1; parts.append(f"{lease}yr lease (short)")

    sc = prop.get("service_charge_pa")
    if sc is not None:
        if sc <= 500:
            score += 0.35; parts.append(f"SC £{sc}/yr (low)")
        elif sc <= 800:
            score += 0.28; parts.append(f"SC £{sc}/yr (reasonable)")
        elif sc <= 1000:
            score += 0.2; parts.append(f"SC £{sc}/yr (moderate)")
        elif sc <= 1200:
            score += 0.14; parts.append(f"SC £{sc}/yr (elevated)")
        elif sc <= 1500:
            score += 0.07; parts.append(f"SC £{sc}/yr (high)")

    gr = prop.get("ground_rent_pa")
    if gr is not None:
        if gr == 0:
            score += 0.25; parts.append("GR peppercorn")
        elif gr <= 100:
            score += 0.2; parts.append(f"GR £{gr}/yr (low)")
        elif gr <= 250:
            score += 0.1; parts.append(f"GR £{gr}/yr (moderate)")

    if tenure == "share_of_freehold":
        score = min(1.0, score + 0.15)
        parts.append("share of freehold bonus")

    return round(max_points * score, 1), ", ".join(parts) if parts else "Leasehold — details unknown"


def score_layout_livability(prop: dict, max_points: float) -> tuple[float, str]:
    """Score based on layout quality indicators."""
    score = 0.0
    text = _get_text(prop)
    parts = []

    beds = prop.get("bedrooms") or 0
    if beds >= 3:
        score += 0.3; parts.append(f"{beds} bed")
    elif beds == 2:
        score += 0.25; parts.append("2 bed")
    elif beds == 1:
        score += 0.15; parts.append("1 bed")

    epc = (prop.get("epc_rating") or "").upper()
    epc_scores = {"A": 0.25, "B": 0.22, "C": 0.18, "D": 0.1, "E": 0.05}
    epc_val = epc_scores.get(epc, 0.08)
    score += epc_val
    parts.append(f"EPC {epc}" if epc else "EPC unknown")

    if any(w in text for w in ["garden", "patio", "terrace", "balcony", "courtyard"]):
        score += 0.2; parts.append("outdoor space")
    elif "communal garden" in text:
        score += 0.1; parts.append("communal garden")

    if any(w in text for w in ["garage", "driveway", "off-street parking", "parking space"]):
        score += 0.15; parts.append("parking")
    elif "permit parking" in text or "on-street" in text:
        score += 0.05

    if any(w in text for w in ["separate lounge", "reception room", "sitting room", "living room"]):
        score += 0.1; parts.append("separate lounge")

    return round(max_points * min(score, 1.0), 1), ", ".join(parts) if parts else "Basic layout"


def score_walkability(enrichment: dict | None, config: dict, max_points: float) -> tuple[float, str]:
    """Score based on walking distances to station and supermarket."""
    if not enrichment:
        return max_points * 0.5, "No walkability data — partial score"

    score = 0.0
    parts = []

    station_min = enrichment.get("nearest_station_walk_min")
    station_name = enrichment.get("nearest_station_name", "Station")
    if station_min is not None:
        if station_min <= 5:
            score += 0.5
        elif station_min <= 10:
            score += 0.4
        elif station_min <= 15:
            score += 0.3
        elif station_min <= 20:
            score += 0.2
        elif station_min <= 25:
            score += 0.1
        parts.append(f"{station_name} {station_min} min")

    # Use nearest_supermarket_* (v3) or fall back to Lidl/Aldi
    preferred_min = config.get("hard_gates", {}).get("supermarket_preferred_walk_min", 20)
    best_super = enrichment.get("nearest_supermarket_walk_min")
    super_name = enrichment.get("nearest_supermarket_name", "Supermarket")
    if best_super is None:
        lidl = enrichment.get("nearest_lidl_walk_min")
        aldi = enrichment.get("nearest_aldi_walk_min")
        candidates = [(x, n) for x, n in [(lidl, "Lidl"), (aldi, "Aldi")] if x is not None]
        if candidates:
            best_super, super_name = min(candidates, key=lambda t: t[0])

    if best_super is not None:
        if best_super <= 10:
            score += 0.35
        elif best_super <= preferred_min:
            score += 0.25
        elif best_super <= 25:
            score += 0.15
        parts.append(f"{super_name} {best_super} min")

    if station_min is not None and best_super is not None:
        if station_min <= 15 and best_super <= 15:
            score += 0.15; parts.append("both close bonus")
        elif station_min <= 20 and best_super <= 20:
            score += 0.1

    return round(max_points * min(score, 1.0), 1), ", ".join(parts) if parts else "Walk data unavailable"


def score_long_term_flexibility(prop: dict, enrichment: dict | None, max_points: float) -> tuple[float, str]:
    """Score based on resale appeal and long-term value."""
    score = 0.0
    text = _get_text(prop)
    parts = []

    tenure = (prop.get("tenure") or "").lower()
    if tenure == "freehold":
        score += 0.4; parts.append("freehold")
    elif tenure == "share_of_freehold":
        score += 0.3; parts.append("share of freehold")
    elif tenure == "leasehold":
        score += 0.15; parts.append("leasehold")

    ptype = (prop.get("property_type") or "").lower()
    if ptype in ("detached", "semi-detached"):
        score += 0.3; parts.append(ptype)
    elif ptype in ("terraced", "bungalow"):
        score += 0.25; parts.append(ptype)
    elif ptype == "flat":
        score += 0.15; parts.append("flat")

    if enrichment:
        london_min = enrichment.get("commute_to_london_min")
        if london_min is not None:
            if london_min <= 45:
                score += 0.2; parts.append(f"London {london_min} min")
            elif london_min <= 60:
                score += 0.15; parts.append(f"London {london_min} min")
            elif london_min <= 90:
                score += 0.1; parts.append(f"London {london_min} min")

    if any(w in text for w in ["chain free", "no chain", "no onward chain"]):
        score += 0.1; parts.append("chain-free")

    return round(max_points * min(score, 1.0), 1), ", ".join(parts) if parts else "Standard long-term profile"


def _get_text(prop: dict) -> str:
    """Get combined lowercase text from description and key features."""
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
