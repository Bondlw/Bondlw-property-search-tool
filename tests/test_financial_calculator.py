"""Tests for FinancialCalculator — mortgage, costs, lease extension, relativity."""

import pytest
from src.utils.financial_calculator import FinancialCalculator


class TestMortgageMonthly:
    """Test mortgage payment calculations."""

    def test_standard_repayment(self, base_config):
        calc = FinancialCalculator(base_config)
        monthly = calc.calculate_mortgage_monthly(175000)
        # Principal: 175000 - 37500 = 137500 at 4.5% over 30yr
        assert 650 < monthly < 750

    def test_deposit_covers_full_price(self, base_config):
        calc = FinancialCalculator(base_config)
        monthly = calc.calculate_mortgage_monthly(37500)
        assert monthly == 0.0

    def test_zero_price(self, base_config):
        calc = FinancialCalculator(base_config)
        monthly = calc.calculate_mortgage_monthly(0)
        assert monthly == 0.0

    def test_zero_interest_rate(self, base_config):
        base_config["user"]["mortgage_rate"] = 0
        calc = FinancialCalculator(base_config)
        monthly = calc.calculate_mortgage_monthly(175000)
        # Principal / num_payments = 137500 / 360
        expected = 137500 / 360
        assert abs(monthly - expected) < 0.01

    def test_higher_price_higher_payment(self, base_config):
        calc = FinancialCalculator(base_config)
        lower = calc.calculate_mortgage_monthly(160000)
        higher = calc.calculate_mortgage_monthly(190000)
        assert higher > lower


class TestTotalMonthlyCost:
    """Test total monthly cost breakdown calculations."""

    def test_freehold_no_charges(self, base_config, freehold_property):
        calc = FinancialCalculator(base_config)
        costs = calc.calculate_total_monthly(freehold_property)
        assert costs["service_charge_monthly"] == 0
        assert costs["ground_rent_monthly"] == 0
        assert costs["mortgage_monthly"] > 0
        assert costs["total_monthly"] > 0

    def test_leasehold_includes_charges(self, base_config, leasehold_property):
        calc = FinancialCalculator(base_config)
        costs = calc.calculate_total_monthly(leasehold_property)
        assert costs["service_charge_monthly"] == 100  # 1200/12
        assert costs["ground_rent_monthly"] == pytest.approx(16.67, abs=0.01)  # 200/12
        assert costs["total_monthly"] > costs["mortgage_monthly"]

    def test_council_tax_band_lookup(self, base_config, freehold_property):
        freehold_property["council_tax_band"] = "C"
        calc = FinancialCalculator(base_config)
        costs = calc.calculate_total_monthly(freehold_property)
        assert costs["council_tax_monthly"] == 125  # Band C monthly

    def test_council_tax_fallback(self, base_config, freehold_property):
        del freehold_property["council_tax_band"]
        calc = FinancialCalculator(base_config)
        costs = calc.calculate_total_monthly(freehold_property)
        assert costs["council_tax_estimated"] is True
        assert costs["council_tax_monthly"] == 109  # Band B default

    def test_within_target_flag(self, base_config, freehold_property):
        freehold_property["price"] = 150000  # Low enough to be within target
        calc = FinancialCalculator(base_config)
        costs = calc.calculate_total_monthly(freehold_property)
        # Cost should be well within target
        if costs["total_monthly"] < base_config["monthly_target"]["min"]:
            assert costs["under_target"] is True


class TestFullMonthlyCost:
    """Test all-in monthly cost including bills."""

    def test_all_in_includes_bills(self, base_config, freehold_property):
        calc = FinancialCalculator(base_config)
        costs = calc.calculate_full_monthly_cost(freehold_property)
        housing = costs["total_monthly"]
        all_in = costs["total_all_in_monthly"]
        bills = base_config["estimated_bills"]["total_monthly"]
        assert all_in == pytest.approx(housing + bills, abs=0.01)

    def test_affordability_rating_green(self, base_config, freehold_property):
        freehold_property["price"] = 140000
        calc = FinancialCalculator(base_config)
        costs = calc.calculate_full_monthly_cost(freehold_property)
        # Very cheap property should be green
        if costs["total_monthly"] < base_config["monthly_target"]["min"]:
            assert costs["affordability_rating"] == "green"


class TestLeaseRelativity:
    """Test the lease relativity lookup — key edge cases from Phase 1 fix."""

    def test_999_year_lease(self):
        assert FinancialCalculator._lease_relativity(999) == 1.0

    def test_150_year_lease(self):
        assert FinancialCalculator._lease_relativity(150) == 0.995

    def test_120_year_lease(self):
        assert FinancialCalculator._lease_relativity(120) == 0.99

    def test_100_year_lease(self):
        assert FinancialCalculator._lease_relativity(100) == 0.97

    def test_80_year_lease(self):
        assert FinancialCalculator._lease_relativity(80) == 0.92

    def test_75_year_marriage_value_boundary(self):
        # Just below 80 — marriage value applies
        assert FinancialCalculator._lease_relativity(75) == 0.88

    def test_50_year_short_lease(self):
        assert FinancialCalculator._lease_relativity(50) == 0.56

    def test_short_lease_monotonically_decreases(self):
        """Verify relativity decreases as lease gets shorter (Phase 1 fix)."""
        previous_value = 1.0
        for years in [150, 120, 100, 90, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 25, 20, 15, 10, 5, 1]:
            current = FinancialCalculator._lease_relativity(years)
            assert current < previous_value, f"Relativity at {years}yr ({current}) should be < at higher ({previous_value})"
            previous_value = current

    def test_5_year_vs_39_year_different(self):
        """Phase 1 critical fix: 5yr and 39yr must NOT produce same relativity."""
        assert FinancialCalculator._lease_relativity(5) != FinancialCalculator._lease_relativity(39)
        assert FinancialCalculator._lease_relativity(5) < FinancialCalculator._lease_relativity(39)

    def test_expired_lease(self):
        assert FinancialCalculator._lease_relativity(0) == 0.0
        assert FinancialCalculator._lease_relativity(-5) == 0.0

    def test_very_short_lease(self):
        r = FinancialCalculator._lease_relativity(1)
        assert r == 0.02
        assert r > 0


class TestLeaseExtensionCost:
    """Test lease extension premium estimation."""

    def test_long_lease_cheap_extension(self, base_config):
        calc = FinancialCalculator(base_config)
        ext = calc.estimate_lease_extension_cost(175000, 100, ground_rent_pa=200)
        assert ext["marriage_value"] == 0  # No marriage value above 80yr
        assert ext["premium"] > 0
        assert ext["total_extension_cost"] == ext["premium"] + 2000

    def test_short_lease_expensive_extension(self, base_config):
        calc = FinancialCalculator(base_config)
        ext = calc.estimate_lease_extension_cost(175000, 60, ground_rent_pa=250)
        assert ext["marriage_value"] > 0  # Marriage value kicks in below 80yr
        # Short lease extension should be significantly more expensive
        long_ext = calc.estimate_lease_extension_cost(175000, 100, ground_rent_pa=250)
        assert ext["premium"] > long_ext["premium"]

    def test_79_year_has_marriage_value(self, base_config):
        calc = FinancialCalculator(base_config)
        ext = calc.estimate_lease_extension_cost(175000, 79)
        assert ext["marriage_value"] > 0

    def test_81_year_no_marriage_value(self, base_config):
        calc = FinancialCalculator(base_config)
        ext = calc.estimate_lease_extension_cost(175000, 81)
        assert ext["marriage_value"] == 0

    def test_extension_cost_includes_fees(self, base_config):
        calc = FinancialCalculator(base_config)
        ext = calc.estimate_lease_extension_cost(175000, 90)
        assert ext["professional_fees"] == 2000
        assert ext["total_extension_cost"] == ext["premium"] + ext["professional_fees"]


class TestStretchImpact:
    """Test stretch impact calculations."""

    def test_returns_results(self, base_config):
        calc = FinancialCalculator(base_config)
        results = calc.calculate_stretch_impact()
        assert len(results) > 0

    def test_extra_monthly_positive(self, base_config):
        calc = FinancialCalculator(base_config)
        results = calc.calculate_stretch_impact()
        for row in results:
            assert row["extra_monthly"] > 0
            assert row["new_price"] == row["base_price"] + row["increment"]


class TestDynamicPriceCap:
    """Test max price calculations."""

    def test_get_dynamic_price_cap(self, base_config):
        calc = FinancialCalculator(base_config)
        cap = calc.get_dynamic_price_cap(service_charge_pa=0, ground_rent_pa=0, council_tax_monthly=109)
        assert cap > 0
        assert cap > 100000

    def test_high_charges_lower_cap(self, base_config):
        calc = FinancialCalculator(base_config)
        cap_low = calc.get_dynamic_price_cap(service_charge_pa=0, ground_rent_pa=0, council_tax_monthly=109)
        cap_high = calc.get_dynamic_price_cap(service_charge_pa=2000, ground_rent_pa=300, council_tax_monthly=140)
        assert cap_high < cap_low

    def test_calculate_max_price_returns_tiers(self, base_config):
        calc = FinancialCalculator(base_config)
        result = calc.calculate_max_price(service_charge_pa=1000, ground_rent_pa=200, council_tax_monthly=109)
        assert "tiers" in result
        assert "green" in result["tiers"]
        assert "amber" in result["tiers"]


class TestDiscountSignals:
    """Test negotiation discount signal logic."""

    def test_no_signals_returns_empty(self, base_config):
        calc = FinancialCalculator(base_config)
        signals, pct = calc._calculate_discount_signals(None, None, [])
        assert signals == []
        assert pct == 0

    def test_stale_listing_180d(self, base_config):
        calc = FinancialCalculator(base_config)
        signals, pct = calc._calculate_discount_signals(180, None, [])
        assert any("Stale" in s for s in signals)
        assert pct >= 7

    def test_60d_listing(self, base_config):
        calc = FinancialCalculator(base_config)
        signals, pct = calc._calculate_discount_signals(60, None, [])
        assert pct >= 3

    def test_short_lease_signal(self, base_config):
        calc = FinancialCalculator(base_config)
        signals, pct = calc._calculate_discount_signals(None, 90, [])
        assert any("Short lease" in s for s in signals)
        assert pct >= 3

    def test_price_cuts_signal(self, base_config):
        calc = FinancialCalculator(base_config)
        history = [{"change_amount": -5000}, {"change_amount": -3000}]
        signals, pct = calc._calculate_discount_signals(None, None, history)
        assert any("price cut" in s.lower() for s in signals)

    def test_discount_capped_at_12(self, base_config):
        calc = FinancialCalculator(base_config)
        history = [{"change_amount": -5000}, {"change_amount": -3000}]
        signals, pct = calc._calculate_discount_signals(200, 80, history)
        assert pct <= 12


class TestNegotiationAnalysis:
    """Test negotiation analysis."""

    def test_no_signals_returns_none(self, base_config, freehold_property):
        calc = FinancialCalculator(base_config)
        result = calc.calculate_negotiation_analysis(freehold_property)
        assert result is None

    def test_with_signals_returns_analysis(self, base_config, freehold_property):
        calc = FinancialCalculator(base_config)
        result = calc.calculate_negotiation_analysis(freehold_property, days_on_market=90)
        assert result is not None
        assert result["suggested_offer"] < freehold_property["price"]
        assert result["discount_pct"] > 0

    def test_zero_price_returns_none(self, base_config):
        calc = FinancialCalculator(base_config)
        result = calc.calculate_negotiation_analysis({"price": 0}, days_on_market=90)
        assert result is None


class TestStretchOpportunity:
    """Test stretch opportunity detection."""

    def test_cheap_property_not_stretch(self, base_config, freehold_property):
        calc = FinancialCalculator(base_config)
        freehold_property["_days_on_market"] = 90
        freehold_property["price"] = 140000
        is_stretch, monthly = calc.is_stretch_opportunity(freehold_property, base_config)
        assert is_stretch is False

    def test_no_dom_not_stretch(self, base_config, freehold_property):
        calc = FinancialCalculator(base_config)
        is_stretch, monthly = calc.is_stretch_opportunity(freehold_property, base_config)
        assert is_stretch is False
