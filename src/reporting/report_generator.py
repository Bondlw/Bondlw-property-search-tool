"""HTML report generator using Jinja2 templates."""

import json
import logging
import math
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..filtering.hard_gates import check_all_gates
from ..filtering.scoring import score_property
from ..utils.financial_calculator import FinancialCalculator
from ..utils.geo import haversine_miles

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generate HTML reports from property data."""

    @staticmethod
    def _json_parse(value):
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return [value] if value else []
        return []

    def __init__(self, config: dict):
        self.config = config
        template_dir = Path(__file__).parent.parent.parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True,
        )
        self.env.filters["currency"] = lambda v: f"£{v:,.0f}" if v else "N/A"
        self.env.filters["json_parse"] = self._json_parse
        # Pre-build area lookup list (name, lat, lng)
        self._area_list = [
            (a["name"], a["lat"], a["lng"])
            for group in self.config.get("search_areas", {}).values()
            for a in group
            if a.get("lat") and a.get("lng")
        ]

    def _nearest_area(self, lat: float, lng: float) -> tuple[str, float]:
        """Return (name, distance_miles) of the nearest configured search area."""
        best_name, best_dist = "Unknown", float("inf")
        for name, a_lat, a_lng in self._area_list:
            dist = haversine_miles(lat, lng, a_lat, a_lng)
            if dist < best_dist:
                best_dist, best_name = dist, name
        return best_name, best_dist
    @staticmethod
    def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Straight-line distance in miles between two lat/lng points."""
        return haversine_miles(lat1, lng1, lat2, lng2)

        # Exposed after generate() for use by caller
        self.last_qualifying: list[dict] = []
        self.last_new_today: list[dict] = []
        self.last_near_misses: list[dict] = []

    def generate(self, properties: list[dict], output_path: str, enrichment_map: dict | None = None,
                 favourite_ids: set[int] | None = None, excluded_ids: set[int] | None = None,
                 price_history_map: dict | None = None,
                 tracking_statuses: dict[int, str] | None = None) -> str:
        """Generate a full daily report. Returns the output file path.

        enrichment_map: optional {property_id: enrichment_dict} to feed into gates.
        favourite_ids: set of property IDs that are favourited.
        excluded_ids: set of property IDs that are excluded.
        """
        today = date.today().isoformat()
        calc = FinancialCalculator(self.config)
        fav_ids = favourite_ids or set()
        excl_ids = excluded_ids or set()
        track_map = tracking_statuses or {}

        qualifying = []
        needs_verification = []
        near_misses = []
        rejected = []
        new_today = []
        stretch = []
        negotiation = []
        favourites = []
        radius_filtered_count = 0
        in_radius_props = []

        for prop in properties:
            prop_id = prop["id"]
            prop["_is_favourite"] = prop_id in fav_ids
            prop["_is_excluded"] = prop_id in excl_ids
            prop["_tracking_status"] = track_map.get(prop_id, "new")
            prop["_is_new"] = prop.get("first_seen_date") == today
            prop["_is_reduced"] = bool(prop.get("price_reduced"))
            prop["_price_history"] = (price_history_map or {}).get(prop_id, [])

            # Build police.uk crime link from postcode
            postcode = (prop.get("postcode") or "").replace(" ", "")
            prop["_crime_link"] = f"https://www.police.uk/pu/your-area/?q={postcode}" if postcode else None

            # Parse floor plans, video, brochure, rooms from DB
            fp_raw = prop.get("floorplan_urls")
            prop["_floor_plans"] = json.loads(fp_raw) if fp_raw else []
            prop["_video_url"] = prop.get("video_url")
            prop["_brochure_url"] = prop.get("brochure_url")
            rooms_raw = prop.get("rooms")
            prop["_rooms"] = json.loads(rooms_raw) if rooms_raw else []

            enrichment = (enrichment_map or {}).get(prop_id) or prop.get("_enrichment")

            # Set defaults for enrichment-dependent fields (avoids template errors when no enrichment)
            prop.setdefault("_nearest_station", None)
            prop.setdefault("_station_walk_min", None)
            prop.setdefault("_commute_london_min", None)
            prop.setdefault("_commute_maidstone_min", None)
            prop.setdefault("_annual_season_ticket", None)
            prop.setdefault("_flood_zone", None)
            prop.setdefault("_broadband_speed", None)
            prop.setdefault("_supermarket_name", None)
            prop.setdefault("_supermarket_walk_min", None)
            prop.setdefault("_avg_sold_price", None)

            passed, gate_results = check_all_gates(prop, enrichment, self.config)

            failed_gates = [g for g in gate_results if not g.passed]
            passed_gates = [g for g in gate_results if g.passed]

            prop["_gate_results"] = gate_results
            prop["_failed_gates"] = failed_gates
            prop["_passed_gates"] = passed_gates
            prop["_gates_passed"] = passed
            prop["_failed_count"] = len(failed_gates)

            # Financial data for every property
            prop["_costs"] = calc.calculate_full_monthly_cost(prop)

            # Crime total from enrichment (for display on every card)
            if enrichment:
                crime = enrichment.get("crime_summary")
                if isinstance(crime, str):
                    try:
                        crime = json.loads(crime)
                    except (json.JSONDecodeError, TypeError):
                        crime = None
                if isinstance(crime, dict):
                    prop["_crime_total"] = sum(int(v) for v in crime.values() if str(v).isdigit())
                else:
                    prop["_crime_total"] = None
            else:
                prop["_crime_total"] = None

            # Enrichment: transport, location, sold prices
            if enrichment:
                prop["_nearest_station"] = enrichment.get("nearest_station_name")
                prop["_station_walk_min"] = enrichment.get("nearest_station_walk_min")
                prop["_commute_london_min"] = enrichment.get("commute_to_london_min")
                prop["_commute_maidstone_min"] = enrichment.get("commute_to_maidstone_min")
                prop["_annual_season_ticket"] = enrichment.get("annual_season_ticket")
                prop["_flood_zone"] = enrichment.get("flood_zone")
                prop["_broadband_speed"] = enrichment.get("broadband_speed_mbps")
                prop["_supermarket_name"] = enrichment.get("nearest_supermarket_name")
                prop["_supermarket_walk_min"] = enrichment.get("nearest_supermarket_walk_min")
                prop["_avg_sold_price"] = enrichment.get("avg_sold_price_nearby")

            # Size: use DB value, or fall back to room dimensions total
            size = prop.get("size_sqft")
            parsed_rooms = prop.get("_rooms", [])

            if not size and parsed_rooms:
                total_sqm = sum(
                    float(r.get("width", 0) or 0) * float(r.get("length", 0) or 0)
                    for r in parsed_rooms
                    if isinstance(r, dict) and r.get("width") and r.get("length")
                )
                if total_sqm > 0:
                    size = int(total_sqm * 10.764)
                    prop["_size_from_rooms"] = True

            prop["_size_sqft"] = size
            prop["_size_sqm"] = round(size / 10.764) if size else None
            prop["_price_per_sqft"] = round(prop["price"] / size) if size else None

            # Office distance (miles, straight-line)
            office_cfg = self.config.get("office")
            if enrichment:
                prop["_commute_maidstone_min"] = enrichment.get("commute_to_maidstone_min")
            if office_cfg and prop.get("latitude") and prop.get("longitude"):
                prop["_office_distance_miles"] = self._haversine_miles(
                    prop["latitude"], prop["longitude"],
                    office_cfg["lat"], office_cfg["lng"],
                )
                prop["_office_name"] = office_cfg.get("name", "Office")
                prop["_office_remote_threshold"] = office_cfg.get("remote_threshold_miles", 20)
            else:
                prop["_office_distance_miles"] = None

            # Coordinates for map view (from base property, not enrichment)
            prop["_latitude"] = prop.get("latitude")
            prop["_longitude"] = prop.get("longitude")

            # Nearest search area (for area filter) + max-radius skip
            lat = prop.get("latitude")
            lng = prop.get("longitude")
            if lat and lng:
                area_name, area_dist = self._nearest_area(lat, lng)
                prop["_search_area"] = area_name
                max_radius = self.config.get("max_radius_miles", 10)
                if area_dist > max_radius:
                    continue
            else:
                prop["_search_area"] = "Unknown"

            radius_filtered_count += 1
            in_radius_props.append(prop)

            # Skip properties with addresses in excluded locations
            excluded_locations = self.config.get("excluded_address_terms", [])
            addr_lower = (prop.get("address") or prop.get("title") or "").lower()
            if any(term.lower() in addr_lower for term in excluded_locations):
                continue

            # Skip excluded from all classification sections
            if prop["_is_excluded"]:
                continue

            # Score every non-excluded property (needed for card display, including favourites)
            if passed:
                prop["_scores"] = score_property(prop, enrichment, self.config)
            else:
                prop["_scores"] = None

            # Days on market and negotiation (needed for all cards)
            days = self._days_on_market(prop)
            prop["_days_on_market"] = days
            prop["_negotiation"] = calc.calculate_negotiation_analysis(prop, days)

            # Recommended offer based on price history + days on market
            prop["_recommended_offer"] = self._compute_recommended_offer(prop, days, calc)

            # Deposit recommendation for this property
            prop["_deposit_rec"] = self._compute_deposit_recommendation(prop, calc)

            # New today
            if prop.get("first_seen_date") == today:
                new_today.append(prop)

            # Track favourites — shown in their own section only (prevents duplicate card IDs)
            # Set qualification label for every property
            neg_check = prop.get("_negotiation")
            offer_qualifies = neg_check and neg_check.get("would_qualify")
            offer_price = neg_check.get("suggested_offer") if neg_check else None
            offer_discount = neg_check.get("discount_pct") if neg_check else None

            if passed:
                has_unverified = any(g.needs_verification for g in gate_results)
                if has_unverified:
                    prop["_qualification_label"] = "qualifies-unverified"
                    prop["_qualification_text"] = "Qualifies at asking (unverified)"
                else:
                    prop["_qualification_label"] = "qualifies-asking"
                    prop["_qualification_text"] = "Qualifies at asking price"
            elif offer_qualifies and offer_price:
                prop["_qualification_label"] = "qualifies-offer"
                prop["_qualification_text"] = f"Qualifies at offer \u00a3{offer_price // 1000:.0f}k (\u2212{offer_discount}%)"
                # Re-score using the offer price so financial fit reflects what you'd actually pay
                offer_prop = {**prop, "price": offer_price}
                prop["_scores"] = score_property(offer_prop, enrichment, self.config)
                prop["_offer_costs"] = calc.calculate_full_monthly_cost(offer_prop)
            else:
                prop["_qualification_label"] = "does-not-qualify"
                prop["_qualification_text"] = "Does not qualify"

            if prop["_is_favourite"]:
                # Classify favourite so its card shows qualifying status
                if passed:
                    has_unverified = any(g.needs_verification for g in gate_results)
                    if has_unverified:
                        prop["_gate_status"] = "needs-verify"
                        prop["_needs_verification"] = True
                        prop["_unverified_fields"] = [g for g in gate_results if g.needs_verification]
                    else:
                        prop["_gate_status"] = "qualifying"
                        prop["_needs_verification"] = False
                else:
                    prop["_gate_status"] = "failed"
                    prop["_needs_verification"] = False
                favourites.append(prop)
                continue

            # Categorise non-favourited properties
            if passed:
                # Check if any gate has needs_verification flag
                has_unverified = any(g.needs_verification for g in gate_results)
                if has_unverified:
                    prop["_needs_verification"] = True
                    prop["_unverified_fields"] = [g for g in gate_results if g.needs_verification]
                    needs_verification.append(prop)
                else:
                    prop["_needs_verification"] = False
                    qualifying.append(prop)
            else:
                asking_rating = (prop.get("_costs") or {}).get("affordability_rating", "red")
                if len(failed_gates) <= 2 and offer_qualifies and asking_rating != "red":
                    near_misses.append(prop)
                else:
                    rejected.append(prop)

            # Stretch opportunities — properties just above the qualifying ceiling
            # that could come into budget with negotiation (listed 60+ days)
            if not passed:
                monthly = prop["_costs"]["total_monthly"]
                monthly_max = self.config.get("monthly_target", {}).get("max", 954)
                negotiation_ceiling = calc.take_home * 0.40  # £1,060 — upper bound for negotiation targets
                neg = prop.get("_negotiation")
                offer_qualifies = neg and neg.get("would_qualify")
                asking_rating = (prop.get("_costs") or {}).get("affordability_rating", "red")
                if days and days >= 60 and monthly_max < monthly <= negotiation_ceiling and offer_qualifies and asking_rating != "red":
                    over_pct_monthly = round(((monthly - monthly_max) / monthly_max) * 100, 1)
                    prop["_over_budget_pct"] = over_pct_monthly
                    prop["_stretch_monthly"] = round(monthly, 0)
                    stretch.append(prop)

            # Negotiation targets — only include if:
            # 1. The negotiated offer would qualify (neg["would_qualify"] == True), AND
            # 2. The only gates that fail are price/affordability (price_cap, monthly_cost).
            # Properties failing lease, SC, CT, crime etc. go to rejected/near-miss only.
            neg = prop["_negotiation"]
            affordability_gates = {"price_cap", "monthly_cost"}
            non_affordability_fails = [g for g in failed_gates if g.gate_name not in affordability_gates]
            is_negotiation_candidate = (
                neg
                and neg["would_qualify"]
                and not passed
                and len(non_affordability_fails) == 0
            )
            if passed or is_negotiation_candidate:
                if neg:
                    negotiation.append(prop)

        # Sort sections: new items first, then by score/failed count
        qualifying.sort(key=lambda p: (not p.get("_is_new"), -(p.get("_scores") or {}).get("total", 0), p.get("_price_per_sqft") or 9999))
        needs_verification.sort(key=lambda p: (not p.get("_is_new"), -(p.get("_scores") or {}).get("total", 0), p.get("_price_per_sqft") or 9999))
        stretch.sort(key=lambda p: (not p.get("_is_new"), p.get("_stretch_monthly", 9999)))

        # Deduplicate negotiation list
        seen_ids = set()
        unique_negotiation = []
        for p in negotiation:
            if p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                unique_negotiation.append(p)

        # Merge stretch + negotiation into "Opportunities"
        opp_ids = set()
        opportunities = []
        for p in unique_negotiation:
            opp_ids.add(p["id"])
            p["_opp_type"] = "negotiation"
            opportunities.append(p)
        for p in stretch:
            if p["id"] not in opp_ids:
                opp_ids.add(p["id"])
                p["_opp_type"] = "stretch"
                opportunities.append(p)
        opportunities.sort(key=lambda p: (
            not p.get("_is_new"),
            0 if p.get("_opp_type") == "negotiation" else 1,
            -(p.get("_scores") or {}).get("total", 0),
            p.get("_stretch_monthly", 9999),
        ))

        # Remove from near_misses any property that already appears in opportunities
        near_misses = [p for p in near_misses if p["id"] not in opp_ids]

        # Near misses: sort by severity — minor/liveable failures first
        # Gates ranked by how "liveable" the failure is (lower = more liveable)
        gate_severity = {
            "monthly_cost": 1,       # slightly over GREEN — very liveable
            "epc_rating": 2,         # can improve; bills slightly higher
            "council_tax_band": 2,   # one band over is manageable
            "station_walkable": 3,   # few min extra walk
            "supermarket_walkable": 3,
            "no_tbc_fields": 3,      # unknown data, might be fine
            "price_cap": 4,          # over budget but negotiable
            "service_charge": 4,
            "ground_rent": 4,
            "lease_length": 7,       # expensive to fix
            "crime_safety": 7,       # safety concern
            "flood_risk": 8,         # insurance/structural
            "not_retirement": 9,     # age restriction
            "not_auction": 9,
            "move_in_ready": 9,      # renovation project
            "not_non_standard": 9,
            "no_doubling_clause": 9,
        }
        for p in near_misses:
            failed = p.get("_failed_gates", [])
            # Worst severity among failed gates
            worst = max((gate_severity.get(g.gate_name, 5) for g in failed), default=5)
            # Average severity
            avg = sum(gate_severity.get(g.gate_name, 5) for g in failed) / max(len(failed), 1)
            p["_severity_worst"] = worst
            p["_severity_avg"] = avg
        near_misses.sort(key=lambda p: (
            not p.get("_is_new"),
            p.get("_severity_worst", 5),
            p.get("_severity_avg", 5),
            p.get("_failed_count", 99),
        ))

        # Area stats (only radius-filtered properties)
        area_stats = self._compute_area_stats(in_radius_props, qualifying + needs_verification)

        # First-import detection
        is_first_import = len(new_today) > 50 and (len(new_today) / max(radius_filtered_count, 1)) > 0.8

        # Stretch impact reference table
        stretch_impact = calc.calculate_stretch_impact()

        # Collect shortlisted properties across all sections
        shortlisted = [p for p in in_radius_props if p.get("_tracking_status") == "shortlisted" and not p.get("_is_excluded")]
        shortlisted.sort(key=lambda p: -(p.get("_scores") or {}).get("total", 0))

        # Similar to reference property — flag properties matching target size/price
        similar_to_target = []
        ref_config = self.config.get("reference_property", {})
        if ref_config.get("enabled"):
            ref_size = ref_config.get("size_sqft", 0)
            ref_price = ref_config.get("price", 0)
            ref_portal_id = ref_config.get("portal_id")
            size_tolerance = ref_config.get("size_tolerance_pct", 15) / 100
            price_tolerance = ref_config.get("price_tolerance_pct", 15) / 100
            size_min = ref_size * (1 - size_tolerance) if ref_size else 0
            size_max = ref_size * (1 + size_tolerance) if ref_size else float("inf")
            price_min = ref_price * (1 - price_tolerance) if ref_price else 0
            price_max = ref_price * (1 + price_tolerance) if ref_price else float("inf")

            for prop in in_radius_props:
                if prop.get("_is_excluded"):
                    continue
                # Skip the reference property itself
                if prop.get("portal_id") == ref_portal_id:
                    continue
                prop_size = prop.get("_size_sqft")
                prop_price = prop.get("price", 0)
                # Must have size data to compare
                if not prop_size:
                    continue
                if size_min <= prop_size <= size_max and price_min <= prop_price <= price_max:
                    # Calculate how similar (% difference from reference)
                    size_diff_pct = abs(prop_size - ref_size) / ref_size * 100 if ref_size else 0
                    price_diff_pct = abs(prop_price - ref_price) / ref_price * 100 if ref_price else 0
                    prop["_ref_size_diff_pct"] = round(size_diff_pct, 1)
                    prop["_ref_price_diff_pct"] = round(price_diff_pct, 1)
                    prop["_ref_similarity"] = round(100 - (size_diff_pct + price_diff_pct) / 2, 1)
                    prop["_is_similar_to_target"] = True
                    similar_to_target.append(prop)

            # Sort by similarity score (highest first)
            similar_to_target.sort(key=lambda p: -p.get("_ref_similarity", 0))

        template = self.env.get_template("daily_report.html")
        qualifying_fav_count = sum(1 for p in favourites if p.get("_gate_status") == "qualifying")
        needs_verify_fav_count = sum(1 for p in favourites if p.get("_gate_status") == "needs-verify")
        html = template.render(
            report_date=today,
            generated_at=datetime.now().strftime("%A %d %B %Y at %H:%M"),
            total_properties=radius_filtered_count,
            qualifying_count=len(qualifying),
            qualifying_fav_count=qualifying_fav_count,
            needs_verification_count=len(needs_verification),
            needs_verify_fav_count=needs_verify_fav_count,
            new_today_count=len(new_today),
            near_miss_count=len(near_misses),
            qualifying=qualifying,
            needs_verification=needs_verification,
            new_today=new_today[:20] if is_first_import else new_today,
            near_misses=near_misses,
            opportunities=opportunities,
            favourites=favourites,
            shortlisted=shortlisted,
            similar_to_target=similar_to_target,
            reference_property=ref_config if ref_config.get("enabled") else None,
            area_stats=area_stats,
            config=self.config,
            is_first_import=is_first_import,
            stretch_impact=stretch_impact,
        )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(html, encoding="utf-8")
        logger.info(f"Report generated: {output_path}")

        # Expose for caller (e.g. notifications)
        self.last_qualifying = qualifying
        self.last_new_today = new_today
        self.last_near_misses = near_misses

        return output_path

    def _days_on_market(self, prop: dict) -> int | None:
        first = prop.get("first_listed_date") or prop.get("first_seen_date")
        if not first:
            return None
        try:
            dt = datetime.strptime(first[:10], "%Y-%m-%d").date()
            return (date.today() - dt).days
        except (ValueError, TypeError):
            return None

    def _compute_recommended_offer(self, prop: dict, days: int | None, calc) -> dict | None:
        """Compute a recommended offer price using shared discount signals plus
        price history context.

        Always returns a result (2% baseline for new listings with no signals).
        """
        price = prop.get("price", 0)
        if not price:
            return None

        history = prop.get("_price_history", [])

        # Calculate total reduction from original asking price
        original_price = price
        total_reduction = 0
        total_reduction_pct = 0.0

        if history:
            original_price = history[0].get("price", price) if isinstance(history[0], dict) else price
            if original_price and original_price != price:
                total_reduction = original_price - price
                total_reduction_pct = round((total_reduction / original_price) * 100, 1)

        # Use shared discount logic
        signals, suggested_discount_pct = calc._calculate_discount_signals(
            days,
            prop.get("lease_years"),
            history,
        )

        # Baseline: even with no signals, recommend a 2% opening offer
        if not signals:
            suggested_discount_pct = 2

        # Calculate offer
        offer_price = round(price * (1 - suggested_discount_pct / 100) / 1000) * 1000
        saving = price - offer_price

        # Calculate all-in at offer price
        offer_prop = {**prop, "price": offer_price}
        offer_costs = calc.calculate_full_monthly_cost(offer_prop)

        return {
            "offer_price": offer_price,
            "discount_pct": suggested_discount_pct,
            "saving": saving,
            "signals": signals,
            "offer_all_in_monthly": offer_costs["total_all_in_monthly"],
            "offer_affordability": offer_costs["affordability_rating"],
            "original_price": original_price if original_price != price else None,
            "total_reduction": total_reduction,
            "total_reduction_pct": total_reduction_pct,
        }

    def _compute_deposit_recommendation(self, prop: dict, calc) -> dict:
        """Compute recommended deposit for a property.

        Strategy: find the deposit that keeps all-in monthly at/below GREEN ceiling.
        If GREEN isn't possible, try AMBER. Show emergency fund remaining.
        """
        price = prop.get("price", 0)
        if not price:
            return {"deposit": calc.deposit, "emergency_fund": 0, "rating": "red"}

        total_savings = self.config["user"].get("total_savings", calc.deposit)
        emergency_target = self.config["user"].get("emergency_fund_target", 5000)
        bills = self.config.get("estimated_bills", {}).get("total_monthly", 198)
        green_ceiling = calc.monthly_target_min + bills
        amber_ceiling = calc.monthly_target_recommended + bills
        stretch_ceiling = calc.monthly_target_max + bills

        # Try deposits from minimum (keeping max emergency fund) to full savings
        # in £500 steps to find the sweet spot
        best = None
        for dep in range(emergency_target, total_savings + 1, 500):
            test_deposit = total_savings - dep  # dep is what we keep back
            if test_deposit < 0:
                continue
            principal = price - test_deposit
            if principal <= 0:
                all_in = bills + self._get_non_mortgage_monthly(prop)
            else:
                r = calc.rate / 12
                n = calc.term_years * 12
                if r == 0:
                    mortgage = principal / n
                else:
                    mortgage = principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
                sc = (prop.get("service_charge_pa") or 0) / 12
                gr = (prop.get("ground_rent_pa") or 0) / 12
                ct = calc._get_ct_monthly(prop)[0]
                all_in = mortgage + sc + gr + ct + bills

            if all_in <= green_ceiling:
                rating = "green"
            elif all_in <= amber_ceiling:
                rating = "amber"
            elif all_in <= stretch_ceiling:
                rating = "stretch"
            else:
                rating = "red"
            entry = {
                "deposit": test_deposit,
                "emergency_fund": total_savings - test_deposit,
                "all_in": round(all_in, 0),
                "rating": rating,
            }
            if rating == "green":
                best = entry
                break  # found the minimum deposit that's GREEN
            if rating == "amber" and not best:
                best = entry

        # Fallback: full deposit
        if not best:
            best = {
                "deposit": total_savings,
                "emergency_fund": 0,
                "all_in": round(prop["_costs"]["total_all_in_monthly"], 0),
                "rating": prop["_costs"]["affordability_rating"],
            }

        return best

    @staticmethod
    def _get_non_mortgage_monthly(prop: dict) -> float:
        sc = (prop.get("service_charge_pa") or 0) / 12
        gr = (prop.get("ground_rent_pa") or 0) / 12
        return sc + gr

    def _compute_area_stats(self, all_props: list, qualifying: list) -> list[dict]:
        """Compute per-area statistics grouped by configured search area."""
        areas = {}
        for prop in all_props:
            area = prop.get("_search_area", "Unknown")
            if area == "Unknown":
                continue
            if area not in areas:
                areas[area] = {
                    "area": area, "total": 0, "qualifying": 0,
                    "prices": [], "crime_totals": [], "days_listed": [],
                }
            areas[area]["total"] += 1
            areas[area]["prices"].append(prop.get("price", 0))

            # Crime total
            crime_total = prop.get("_crime_total")
            if crime_total is not None:
                areas[area]["crime_totals"].append(crime_total)

            # Days on market
            dom = prop.get("_days_on_market")
            if dom is not None:
                areas[area]["days_listed"].append(dom)

        for prop in qualifying:
            area = prop.get("_search_area", "Unknown")
            if area in areas:
                areas[area]["qualifying"] += 1

        stats = []
        for area, data in sorted(areas.items(), key=lambda x: -x[1]["qualifying"]):
            prices = [p for p in data["prices"] if p > 0]
            crime = data["crime_totals"]
            days = data["days_listed"]
            stats.append({
                "area": data["area"],
                "total": data["total"],
                "qualifying": data["qualifying"],
                "avg_price": int(sum(prices) / len(prices)) if prices else 0,
                "min_price": min(prices) if prices else 0,
                "max_price": max(prices) if prices else 0,
                "avg_crime": round(sum(crime) / len(crime), 1) if crime else None,
                "avg_days_listed": round(sum(days) / len(days), 0) if days else None,
            })
        return stats
