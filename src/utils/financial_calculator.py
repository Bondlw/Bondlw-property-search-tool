"""Mortgage and affordability calculations.

Housing-only tiers (before bills):
  GREEN:  housing ≤30% of take-home (≤£795)
  AMBER:  housing 30-33.5% (£795-£889) — qualifying max
  RED:    housing >33.5% (>£889)
  35%:    £928 — hard caution threshold
  40%:    £1,060 — stretch ceiling (negotiation only)

All-in (housing + £198 bills):
  GREEN: ≤£993/mo
  AMBER: £993-£1,087/mo
  RED:   >£1,087/mo
"""

import math


class FinancialCalculator:
    """Calculate mortgage payments and total monthly costs."""

    def __init__(self, config: dict):
        self.config = config
        self.deposit = config["user"]["deposit"]
        self.income = config["user"]["annual_income"]
        self.take_home = config["user"]["monthly_take_home"]
        self.rate = config["user"]["mortgage_rate"] / 100  # Convert percentage
        self.term_years = config["user"]["mortgage_term_years"]
        self.monthly_target_min = config["monthly_target"]["min"]
        self.monthly_target_max = config["monthly_target"]["max"]

    def calculate_mortgage_monthly(self, property_price: int) -> float:
        """Calculate monthly repayment mortgage payment."""
        principal = property_price - self.deposit
        if principal <= 0:
            return 0.0

        monthly_rate = self.rate / 12
        num_payments = self.term_years * 12

        if monthly_rate == 0:
            return principal / num_payments

        # M = P * [r(1+r)^n] / [(1+r)^n - 1]
        payment = principal * (
            monthly_rate * math.pow(1 + monthly_rate, num_payments)
        ) / (
            math.pow(1 + monthly_rate, num_payments) - 1
        )
        return round(payment, 2)

    def _get_ct_monthly(self, property_data: dict) -> tuple[float, bool]:
        """Get council tax monthly from property data or estimate from band.
        
        Returns (amount, is_estimated) where is_estimated=True means we used a fallback.
        """
        ct_annual = property_data.get("council_tax_annual_estimate")
        if ct_annual:
            return round(ct_annual / 12, 2), False

        # Try to estimate from band using config lookup
        band = property_data.get("council_tax_band")
        ct_estimates = self.config.get("council_tax_estimates", {})
        if band:
            band_data = ct_estimates.get(band.upper())
            if band_data:
                return band_data.get("monthly", 0), False

        # No band known — use Band B as conservative estimate for Kent
        fallback = ct_estimates.get("B", {}).get("monthly", 109)
        return fallback, True

    def calculate_total_monthly(self, property_data: dict) -> dict:
        """Calculate full monthly cost breakdown."""
        price = property_data.get("price", 0)
        mortgage = self.calculate_mortgage_monthly(price)

        sc_annual = property_data.get("service_charge_pa") or 0
        gr_annual = property_data.get("ground_rent_pa") or 0

        sc_monthly = round(sc_annual / 12, 2)
        gr_monthly = round(gr_annual / 12, 2)
        ct_monthly, ct_estimated = self._get_ct_monthly(property_data)

        total = mortgage + sc_monthly + gr_monthly + ct_monthly

        return {
            "mortgage_monthly": mortgage,
            "service_charge_monthly": sc_monthly,
            "ground_rent_monthly": gr_monthly,
            "council_tax_monthly": ct_monthly,
            "council_tax_estimated": ct_estimated,
            "total_monthly": round(total, 2),
            "within_target": self.monthly_target_min <= total <= self.monthly_target_max,
            "under_target": total < self.monthly_target_min,
            "over_target": total > self.monthly_target_max,
        }

    def calculate_full_monthly_cost(self, property_data: dict) -> dict:
        """Calculate full monthly cost including estimated bills and living costs.

        Returns housing cost, all-in cost (housing + bills), true all-in cost
        (housing + bills + living costs), and affordability metrics.
        """
        housing = self.calculate_total_monthly(property_data)
        bills = self.config.get("estimated_bills", {}).get("total_monthly", 198)
        living_costs_config = self.config.get("living_costs", {})
        living_costs = living_costs_config.get("total_monthly", 340)
        savings_target = living_costs_config.get("savings_target_monthly", 300)

        housing_total = housing["total_monthly"]
        all_in = round(housing_total + bills, 2)
        true_all_in = round(all_in + living_costs, 2)

        housing_pct = round((housing_total / self.take_home) * 100, 1) if self.take_home else 0
        all_in_pct = round((all_in / self.take_home) * 100, 1) if self.take_home else 0
        true_all_in_pct = round((true_all_in / self.take_home) * 100, 1) if self.take_home else 0
        remaining = round(self.take_home - all_in, 2)
        true_remaining = round(self.take_home - true_all_in, 2)
        after_savings = round(true_remaining - savings_target, 2)

        rating = self.get_affordability_rating(all_in)

        return {
            **housing,
            "estimated_bills_monthly": bills,
            "total_all_in_monthly": all_in,
            "living_costs_monthly": living_costs,
            "true_all_in_monthly": true_all_in,
            "housing_pct_take_home": housing_pct,
            "all_in_pct_take_home": all_in_pct,
            "true_all_in_pct_take_home": true_all_in_pct,
            "remaining_monthly": remaining,
            "true_remaining_monthly": true_remaining,
            "savings_target_monthly": savings_target,
            "after_savings_monthly": after_savings,
            "affordability_rating": rating,
        }

    def get_affordability_rating(self, all_in_monthly: float) -> str:
        """Return green/amber/red based on all-in cost (housing + bills) vs monthly targets."""
        bills = self.config.get("estimated_bills", {}).get("total_monthly", 198)
        green_ceiling = self.monthly_target_min + bills
        amber_ceiling = self.monthly_target_max + bills

        if all_in_monthly <= green_ceiling:
            return "green"
        elif all_in_monthly <= amber_ceiling:
            return "amber"
        return "red"

    def calculate_stretch_impact(self) -> list[dict]:
        """Show what +£5k/+£10k/+£15k means in monthly terms."""
        base_prices = [165000, 170000, 175000]
        increments = [5000, 10000, 15000]
        results = []

        for base in base_prices:
            base_mortgage = self.calculate_mortgage_monthly(base)
            for inc in increments:
                new_mortgage = self.calculate_mortgage_monthly(base + inc)
                extra = round(new_mortgage - base_mortgage, 2)
                results.append({
                    "base_price": base,
                    "increment": inc,
                    "new_price": base + inc,
                    "extra_monthly": extra,
                    "new_mortgage_monthly": new_mortgage,
                })
        return results

    def estimate_lease_extension_cost(
        self,
        property_price: int,
        lease_years_remaining: int,
        ground_rent_pa: float = 0,
        capitalisation_rate: float = 5.0,
        relativity_source: str = "graphs_of_relativity",
    ) -> dict:
        """Estimate the premium for a statutory lease extension (90yr added, peppercorn GR).

        Uses the simplified Leasehold Advisory Service approach:
          1. Capitalised ground rent = PV of ground rent over remaining term
          2. Reversion = PV of freehold interest at end of current lease
          3. Marriage value = 50% of gain if lease < 80yr (zero above 80yr)

        The relativity (short-lease value as % of freehold value) is estimated
        from Gerald Eve / RICS Graphs of Relativity.  Above 80yr the ratio is
        high (90-99%) so the marriage value component is zero and the premium
        is modest.

        Args:
            property_price: Current asking/market price of the property.
            lease_years_remaining: Years left on the lease.
            ground_rent_pa: Current annual ground rent (£).
            capitalisation_rate: Yield used to capitalise ground rent (default 5%).
            relativity_source: Which relativity table to use (only 'graphs_of_relativity').

        Returns dict with premium breakdown and total estimated cost including
        professional fees (~£2k solicitor + valuer).
        """
        cap_rate = capitalisation_rate / 100

        # --- 1. Capitalised ground rent (PV of annuity) ---
        if ground_rent_pa > 0 and cap_rate > 0:
            capitalised_ground_rent = ground_rent_pa * (
                (1 - math.pow(1 + cap_rate, -lease_years_remaining)) / cap_rate
            )
        else:
            capitalised_ground_rent = 0

        # --- 2. Reversion (PV of freehold at end of current lease) ---
        # Freehold value ≈ property price / relativity
        relativity = self._lease_relativity(lease_years_remaining)
        freehold_value = property_price / relativity if relativity > 0 else property_price
        reversion = freehold_value * math.pow(1 + cap_rate, -lease_years_remaining)

        # --- 3. Marriage value (only if lease < 80yr) ---
        marriage_value = 0
        if lease_years_remaining < 80:
            # Extended lease relativity (current + 90yr)
            extended_years = lease_years_remaining + 90
            extended_relativity = self._lease_relativity(extended_years)
            extended_value = freehold_value * extended_relativity

            # Marriage value = 50% of (extended value - current value - landlord's current interest)
            landlord_current = capitalised_ground_rent + reversion
            gain = extended_value - property_price - landlord_current
            if gain > 0:
                marriage_value = gain * 0.5

        premium = round(capitalised_ground_rent + reversion + marriage_value)

        # Professional fees: solicitor (~£1,200) + surveyor/valuer (~£800)
        professional_fees = 2000

        return {
            "premium": premium,
            "capitalised_ground_rent": round(capitalised_ground_rent),
            "reversion": round(reversion),
            "marriage_value": round(marriage_value),
            "professional_fees": professional_fees,
            "total_extension_cost": premium + professional_fees,
            "freehold_value_estimate": round(freehold_value),
            "relativity_pct": round(relativity * 100, 1),
            "lease_years_remaining": lease_years_remaining,
        }

    @staticmethod
    def _lease_relativity(years_remaining: int) -> float:
        """Return the relativity (lease value as fraction of freehold value).

        Based on RICS / Gerald Eve Graphs of Relativity — simplified lookup.
        Returns a decimal, e.g. 0.95 means 95% of freehold value.
        """
        # Piecewise approximation from published graphs
        if years_remaining >= 999:
            return 1.0
        if years_remaining >= 150:
            return 0.995
        if years_remaining >= 120:
            return 0.99
        if years_remaining >= 100:
            return 0.97
        if years_remaining >= 90:
            return 0.95
        if years_remaining >= 80:
            return 0.92
        if years_remaining >= 75:
            return 0.88
        if years_remaining >= 70:
            return 0.84
        if years_remaining >= 65:
            return 0.79
        if years_remaining >= 60:
            return 0.73
        if years_remaining >= 55:
            return 0.65
        if years_remaining >= 50:
            return 0.56
        if years_remaining >= 45:
            return 0.48
        if years_remaining >= 40:
            return 0.40
        if years_remaining >= 35:
            return 0.33
        if years_remaining >= 30:
            return 0.25
        if years_remaining >= 25:
            return 0.20
        if years_remaining >= 20:
            return 0.15
        if years_remaining >= 15:
            return 0.10
        if years_remaining >= 10:
            return 0.08
        if years_remaining >= 5:
            return 0.05
        if years_remaining > 0:
            return 0.02
        return 0.0  # Expired lease — no value

    def _mortgage_multiplier(self) -> float:
        """Return the monthly payment per £1 of mortgage principal.

        For annuity formula: r(1+r)^n / ((1+r)^n - 1)
        """
        monthly_rate = self.rate / 12
        num_payments = self.term_years * 12
        if monthly_rate == 0:
            return 1 / num_payments
        power = math.pow(1 + monthly_rate, num_payments)
        return monthly_rate * power / (power - 1)

    def calculate_max_price(
        self,
        service_charge_pa: float = 0,
        ground_rent_pa: float = 0,
        council_tax_monthly: float | None = None,
    ) -> dict:
        """Calculate the maximum property price for each affordability tier.

        Works backwards from the monthly housing ceiling:
          housing_budget = ceiling - SC/mo - GR/mo - CT/mo
          max_mortgage   = housing_budget / multiplier
          max_price      = max_mortgage + deposit

        Returns GREEN, AMBER, and RED thresholds with full cost breakdowns.
        """
        ct_monthly = council_tax_monthly
        if ct_monthly is None:
            ct_monthly = self.config.get("council_tax_estimates", {}).get("B", {}).get("monthly", 109)

        sc_monthly = round(service_charge_pa / 12, 2)
        gr_monthly = round(ground_rent_pa / 12, 2)
        fixed_monthly = sc_monthly + gr_monthly + ct_monthly

        multiplier = self._mortgage_multiplier()
        bills = self.config.get("estimated_bills", {}).get("total_monthly", 198)
        living_costs = self.config.get("living_costs", {}).get("total_monthly", 340)
        savings_target = self.config.get("living_costs", {}).get("savings_target_monthly", 350)

        tiers = {}
        for tier_name, housing_ceiling in [
            ("green", self.monthly_target_min),
            ("amber", self.monthly_target_max),
            ("red_35pct", round(self.take_home * 0.35)),
            ("stretch_40pct", round(self.take_home * 0.40)),
        ]:
            mortgage_budget = housing_ceiling - fixed_monthly
            if mortgage_budget <= 0:
                tiers[tier_name] = {
                    "max_price": 0,
                    "max_mortgage": 0,
                    "housing_ceiling": housing_ceiling,
                    "mortgage_monthly": 0,
                    "fixed_costs_monthly": round(fixed_monthly, 2),
                    "all_in_monthly": round(fixed_monthly + bills, 2),
                    "remaining_after_all": round(self.take_home - fixed_monthly - bills - living_costs, 2),
                    "after_savings": round(self.take_home - fixed_monthly - bills - living_costs - savings_target, 2),
                    "housing_pct": round((fixed_monthly / self.take_home) * 100, 1),
                    "note": "Fixed costs alone exceed housing ceiling",
                }
                continue

            max_mortgage = mortgage_budget / multiplier
            max_price = round(max_mortgage + self.deposit)
            # Round down to nearest £500 for clean numbers
            max_price = (max_price // 500) * 500

            actual_mortgage = self.calculate_mortgage_monthly(max_price)
            actual_housing = actual_mortgage + fixed_monthly
            actual_all_in = actual_housing + bills
            true_all_in = actual_all_in + living_costs
            remaining = self.take_home - actual_all_in
            true_remaining = self.take_home - true_all_in
            after_savings = true_remaining - savings_target

            tiers[tier_name] = {
                "max_price": max_price,
                "max_mortgage": round(max_mortgage, 0),
                "housing_ceiling": housing_ceiling,
                "mortgage_monthly": actual_mortgage,
                "fixed_costs_monthly": round(fixed_monthly, 2),
                "sc_monthly": sc_monthly,
                "gr_monthly": gr_monthly,
                "ct_monthly": ct_monthly,
                "housing_total_monthly": round(actual_housing, 2),
                "all_in_monthly": round(actual_all_in, 2),
                "true_all_in_monthly": round(true_all_in, 2),
                "remaining_monthly": round(remaining, 2),
                "true_remaining_monthly": round(true_remaining, 2),
                "after_savings": round(after_savings, 2),
                "housing_pct": round((actual_housing / self.take_home) * 100, 1),
            }

        return {
            "deposit": self.deposit,
            "mortgage_rate": self.rate * 100,
            "term_years": self.term_years,
            "take_home": self.take_home,
            "bills_monthly": bills,
            "living_costs_monthly": living_costs,
            "savings_target_monthly": savings_target,
            "service_charge_pa": service_charge_pa,
            "ground_rent_pa": ground_rent_pa,
            "council_tax_monthly": ct_monthly,
            "tiers": tiers,
        }

    def get_dynamic_price_cap(
        self,
        service_charge_pa: float = 0,
        ground_rent_pa: float = 0,
        council_tax_monthly: float | None = None,
    ) -> int:
        """Return the maximum affordable price (AMBER ceiling) for this cost profile."""
        result = self.calculate_max_price(service_charge_pa, ground_rent_pa, council_tax_monthly)
        return result["tiers"]["amber"]["max_price"]



    def _calculate_discount_signals(
        self,
        days_on_market: int | None,
        lease_years: int | None,
        price_history: list | None = None,
    ) -> tuple[list[str], int]:
        """Calculate discount percentage and negotiation signals from property attributes.

        Multi-factor discount:
          - Days on market: 30-59d → 2%, 60-89d → 3%, 90-119d → 4%, 120-179d → 5%, 180+d → 7%
          - Short lease (<100yr): +3%, sub-120yr: +1%
          - Price history reductions: 1 cut → +2%, 2+ cuts → +3%
        Returns (signals, discount_pct) — capped at 12%.
        """
        signals: list[str] = []
        discount_pct = 0

        # Days on market signal
        if days_on_market and days_on_market >= 180:
            signals.append(f"Stale listing ({days_on_market}d)")
            discount_pct += 7
        elif days_on_market and days_on_market >= 120:
            signals.append(f"Long-listed ({days_on_market}d)")
            discount_pct += 5
        elif days_on_market and days_on_market >= 90:
            signals.append(f"Listed {days_on_market}d")
            discount_pct += 4
        elif days_on_market and days_on_market >= 60:
            signals.append(f"Listed {days_on_market}d")
            discount_pct += 3
        elif days_on_market and days_on_market >= 30:
            signals.append(f"Listed {days_on_market}d")
            discount_pct += 2

        # Short lease signal
        if lease_years and lease_years < 100:
            signals.append(f"Short lease ({lease_years}yr)")
            discount_pct += 3
        elif lease_years and lease_years < 120:
            signals.append("Sub-120yr lease")
            discount_pct += 1

        # Price reduction history
        reductions_count = sum(
            1 for entry in (price_history or [])
            if isinstance(entry, dict) and (entry.get("change_amount") or 0) < 0
        )
        if reductions_count >= 2:
            signals.append(f"{reductions_count} price cuts")
            discount_pct += 3
        elif reductions_count == 1:
            signals.append("Price cut once")
            discount_pct += 2

        return signals, min(discount_pct, 12)

    def calculate_negotiation_analysis(
        self, property_data: dict, days_on_market: int | None = None
    ) -> dict | None:
        """Suggest a negotiation price and analyse the financial impact.

        Uses shared discount signals (DOM, lease, price history).
        Returns None if no negotiation signals are present.
        """
        price = property_data.get("price", 0)
        if not price:
            return None

        signals, discount_pct = self._calculate_discount_signals(
            days_on_market,
            property_data.get("lease_years"),
            property_data.get("_price_history", []),
        )

        # No signals — no negotiation analysis
        if not signals:
            return None

        # Round offer to nearest £1k
        offer_price = round(price * (1 - discount_pct / 100) / 1000) * 1000
        saving = price - offer_price

        offer_prop = {**property_data, "price": offer_price}
        offer_costs = self.calculate_full_monthly_cost(offer_prop)

        # Check if offer price passes dynamic affordability cap
        service_charge_pa = property_data.get("service_charge_pa") or 0
        ground_rent_pa = property_data.get("ground_rent_pa") or 0
        ct_monthly, _ = self._get_ct_monthly(property_data)
        dynamic_cap = self.get_dynamic_price_cap(service_charge_pa, ground_rent_pa, ct_monthly)
        price_cap_pass = offer_price <= dynamic_cap

        monthly_would_qualify = offer_costs["total_monthly"] <= self.monthly_target_max
        would_qualify = price_cap_pass and monthly_would_qualify

        notes = []
        if not price_cap_pass:
            notes.append(f"Still above price cap at £{offer_price:,}")
        if not monthly_would_qualify:
            notes.append(f"Monthly £{offer_costs['total_monthly']:,.0f} still over £{self.monthly_target_max} qualifying ceiling")

        return {
            "suggested_offer": offer_price,
            "discount_pct": discount_pct,
            "saving": saving,
            "days_on_market": days_on_market,
            "signals": signals,
            "offer_mortgage_monthly": offer_costs["mortgage_monthly"],
            "offer_housing_monthly": offer_costs["total_monthly"],
            "offer_all_in_monthly": offer_costs["total_all_in_monthly"],
            "offer_affordability_rating": offer_costs["affordability_rating"],
            "would_qualify": would_qualify,
            "notes": notes,
        }

    def is_stretch_opportunity(
        self, property_data: dict, config: dict
    ) -> tuple[bool, float | None]:
        """Check if a property is a stretch opportunity based on monthly cost.

        Stretch = monthly housing cost > AMBER max (£889) but ≤ 40% ceiling (~£1,060).
        """
        stretch = config.get("stretch", {})
        min_days = stretch.get("min_days_on_market", 60)
        days_on_market = property_data.get("_days_on_market")

        if days_on_market is None or days_on_market < min_days:
            return False, None

        costs = self.calculate_total_monthly(property_data)
        monthly = costs["total_monthly"]

        # Stretch: above AMBER but within hard ceiling (~40% of take-home)
        stretch_ceiling = self.take_home * 0.40  # ~£1,060
        if self.monthly_target_max < monthly <= stretch_ceiling:
            return True, monthly

        return False, None
