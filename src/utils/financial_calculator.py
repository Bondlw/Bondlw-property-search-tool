"""Mortgage and affordability calculations.

30/35 budgeting rule (housing-only, before bills):
  GREEN: housing ≤30% of take-home (≤£795)
  AMBER: housing 30-35% of take-home (£795-£928)
  RED:   housing >35% of take-home (>£928)

All-in (housing + £211 bills):
  GREEN: ≤£1,006/mo
  AMBER: £1,006-£1,139/mo
  RED:   >£1,139/mo
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
        """Calculate full monthly cost including estimated bills.

        Returns housing cost AND total all-in cost with affordability rating.
        """
        housing = self.calculate_total_monthly(property_data)
        bills = self.config.get("estimated_bills", {}).get("total_monthly", 211)

        housing_total = housing["total_monthly"]
        all_in = round(housing_total + bills, 2)

        housing_pct = round((housing_total / self.take_home) * 100, 1) if self.take_home else 0
        all_in_pct = round((all_in / self.take_home) * 100, 1) if self.take_home else 0
        remaining = round(self.take_home - all_in, 2)

        rating = self.get_affordability_rating(all_in)

        return {
            **housing,
            "estimated_bills_monthly": bills,
            "total_all_in_monthly": all_in,
            "housing_pct_take_home": housing_pct,
            "all_in_pct_take_home": all_in_pct,
            "remaining_monthly": remaining,
            "affordability_rating": rating,
        }

    def get_affordability_rating(self, all_in_monthly: float) -> str:
        """Return green/amber/red based on all-in cost (housing + bills) vs monthly targets."""
        bills = self.config.get("estimated_bills", {}).get("total_monthly", 211)
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

    def is_within_budget(self, price: int, tenure: str, service_charge_pa: int = 0, config: dict = None) -> tuple[bool, str]:
        """Check if price is within budget caps for the given tenure."""
        if config is None:
            return True, "No config provided"

        budget = config.get("budget", {})

        if tenure == "freehold":
            caps = budget.get("freehold", {})
            absolute_max = caps.get("absolute_max", 200000)
            if price > absolute_max:
                return False, f"Price £{price:,} exceeds freehold cap £{absolute_max:,}"
            return True, "Within freehold budget"

        elif tenure in ("leasehold", "share_of_freehold"):
            caps = budget.get("leasehold", {})
            absolute_max = caps.get("absolute_max", 180000)
            sc_cap_for_max = caps.get("service_charge_cap_for_absolute_max", 900)
            responsible_max = caps.get("responsible_max", 170000)

            if price > absolute_max:
                return False, f"Price £{price:,} exceeds leasehold cap £{absolute_max:,}"

            if price > responsible_max and service_charge_pa >= sc_cap_for_max:
                return False, (
                    f"Price £{price:,} above £{responsible_max:,} requires "
                    f"SC < £{sc_cap_for_max}/yr, but SC is £{service_charge_pa}/yr"
                )
            return True, "Within leasehold budget"

        return False, f"Unknown tenure: {tenure}"

    def calculate_negotiation_analysis(
        self, property_data: dict, days_on_market: int | None = None
    ) -> dict | None:
        """Suggest a negotiation price and analyse the financial impact.

        Discount tiers by days on market:
          30–59d → 5%, 60–89d → 8%, 90+d → 10%
        Returns None if property has been on market < 30 days.
        """
        if not days_on_market or days_on_market < 30:
            return None

        price = property_data.get("price", 0)
        if not price:
            return None

        if days_on_market >= 90:
            discount_pct = 10
        elif days_on_market >= 60:
            discount_pct = 8
        else:
            discount_pct = 5

        # Round offer to nearest £1k
        offer_price = round(price * (1 - discount_pct / 100) / 1000) * 1000

        offer_prop = {**property_data, "price": offer_price}
        offer_costs = self.calculate_full_monthly_cost(offer_prop)

        # Check if offer price passes the price cap
        tenure = (property_data.get("tenure") or "").lower()
        budget = self.config.get("budget", {})
        price_cap_pass = True
        if tenure == "freehold":
            price_cap = budget.get("freehold", {}).get("absolute_max", 200000)
            price_cap_pass = offer_price <= price_cap
        elif tenure in ("leasehold", "share_of_freehold"):
            price_cap = budget.get("leasehold", {}).get("absolute_max", 180000)
            price_cap_pass = offer_price <= price_cap

        monthly_would_qualify = offer_costs["total_monthly"] <= self.monthly_target_min
        would_qualify = price_cap_pass and monthly_would_qualify

        notes = []
        if not price_cap_pass:
            notes.append(f"Still above price cap at £{offer_price:,}")
        if not monthly_would_qualify:
            notes.append(f"Monthly £{offer_costs['total_monthly']:,.0f} still over £{self.monthly_target_min} GREEN target")

        return {
            "suggested_offer": offer_price,
            "discount_pct": discount_pct,
            "days_on_market": days_on_market,
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

        Stretch = monthly housing cost > AMBER max (£928) but ≤ hard ceiling (£1,050).
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
