"""Tests for the 100-point scoring engine."""

import pytest
from src.filtering.scoring import (
    score_property,
    score_financial_fit,
    score_crime_safety,
    score_cost_predictability,
    score_layout_livability,
    score_walkability,
    score_long_term_flexibility,
)


class TestFinancialFitScore:
    """Test financial fit scoring (30 points max)."""

    def test_cheap_property_full_marks(self, base_config):
        prop = {"price": 140000, "council_tax_band": "A"}
        score, reason = score_financial_fit(prop, base_config, 30)
        assert score == 30
        assert "Green" in reason

    def test_expensive_property_low_score(self, base_config):
        prop = {"price": 200000, "council_tax_band": "D", "service_charge_pa": 1500, "ground_rent_pa": 300}
        score, reason = score_financial_fit(prop, base_config, 30)
        assert score < 15

    def test_score_never_negative(self, base_config):
        prop = {"price": 500000, "council_tax_band": "H", "service_charge_pa": 5000}
        score, reason = score_financial_fit(prop, base_config, 30)
        assert score >= 0

    def test_score_never_exceeds_max(self, base_config):
        prop = {"price": 50000, "council_tax_band": "A"}
        score, reason = score_financial_fit(prop, base_config, 30)
        assert score <= 30


class TestCrimeSafetyScore:
    """Test crime safety scoring (25 points max)."""

    def test_no_enrichment_partial_score(self):
        score, reason = score_crime_safety(None, 25)
        assert score == 12.5  # 50% of max
        assert "No crime data" in reason

    def test_good_safety_high_score(self, basic_enrichment):
        basic_enrichment["crime_safety_score"] = 0.9
        score, reason = score_crime_safety(basic_enrichment, 25)
        assert score > 15

    def test_bad_safety_low_score(self, basic_enrichment):
        basic_enrichment["crime_safety_score"] = 0.2
        basic_enrichment["crime_summary"] = '{"violent": 20, "asb": 25, "burglary": 10, "drugs": 10, "other": 15}'
        score, reason = score_crime_safety(basic_enrichment, 25)
        assert score < 15

    def test_no_crime_summary_partial(self):
        enrichment = {"crime_safety_score": 0.5}
        score, reason = score_crime_safety(enrichment, 25)
        assert score == 12.5

    def test_invalid_json_partial(self):
        enrichment = {"crime_summary": "invalid json"}
        score, reason = score_crime_safety(enrichment, 25)
        assert score == 12.5

    def test_zero_crime_full_marks(self, basic_enrichment):
        basic_enrichment["crime_summary"] = '{"violent": 0, "asb": 0, "burglary": 0, "drugs": 0, "other": 0}'
        score, reason = score_crime_safety(basic_enrichment, 25)
        assert score == 25


class TestCostPredictability:
    """Test cost predictability scoring (15 points max)."""

    def test_freehold_full_marks(self):
        prop = {"tenure": "freehold"}
        score, reason = score_cost_predictability(prop, 15)
        assert score == 15

    def test_leasehold_with_charges(self):
        prop = {"tenure": "leasehold", "service_charge_pa": 1500, "ground_rent_pa": 200}
        score, reason = score_cost_predictability(prop, 15)
        assert 0 <= score <= 15


class TestLayoutLivability:
    """Test layout livability scoring (15 points max)."""

    def test_spacious_property_high_score(self):
        prop = {
            "bedrooms": 3,
            "size_sqft": 900,
            "property_type": "House",
            "description": "A spacious 3 bed house with large garden and garage",
            "key_features": '["Garden", "Garage", "Storage"]',
        }
        score, reason = score_layout_livability(prop, 15)
        assert score > 8

    def test_score_within_range(self):
        prop = {"bedrooms": 2, "property_type": "Flat", "description": "A 2 bed flat"}
        score, reason = score_layout_livability(prop, 15)
        assert 0 <= score <= 15


class TestWalkability:
    """Test walkability scoring (10 points max)."""

    def test_no_enrichment_partial(self, base_config):
        score, reason = score_walkability(None, base_config, 10)
        assert score == 5  # 50% of max

    def test_close_station_high_score(self, base_config, basic_enrichment):
        basic_enrichment["nearest_station_walk_min"] = 5
        basic_enrichment["nearest_supermarket_walk_min"] = 5
        score, reason = score_walkability(basic_enrichment, base_config, 10)
        assert score >= 8


class TestLongTermFlexibility:
    """Test long-term flexibility scoring (5 points max)."""

    def test_freehold_good_score(self, basic_enrichment):
        prop = {"tenure": "freehold", "bedrooms": 3, "property_type": "Semi-detached"}
        basic_enrichment["commute_to_london_min"] = 40
        score, reason = score_long_term_flexibility(prop, basic_enrichment, 5)
        assert score > 2

    def test_score_within_range(self, basic_enrichment):
        prop = {"tenure": "leasehold", "lease_years": 85, "bedrooms": 1}
        score, reason = score_long_term_flexibility(prop, basic_enrichment, 5)
        assert 0 <= score <= 5


class TestScoreProperty:
    """Integration test — full property scoring."""

    def test_total_is_sum_of_components(self, freehold_property, basic_enrichment, base_config):
        result = score_property(freehold_property, basic_enrichment, base_config)
        component_sum = (
            result["financial_fit"]
            + result["crime_safety"]
            + result["cost_predictability"]
            + result["layout_livability"]
            + result["walkability"]
            + result["long_term_flexibility"]
        )
        assert result["total"] == pytest.approx(component_sum, abs=0.1)

    def test_total_within_bounds(self, freehold_property, basic_enrichment, base_config):
        result = score_property(freehold_property, basic_enrichment, base_config)
        assert 0 <= result["total"] <= 100

    def test_all_reasons_present(self, freehold_property, basic_enrichment, base_config):
        result = score_property(freehold_property, basic_enrichment, base_config)
        for component in ["financial_fit", "crime_safety", "cost_predictability", "layout_livability", "walkability", "long_term_flexibility"]:
            assert f"{component}_reason" in result
            assert isinstance(result[f"{component}_reason"], str)
            assert len(result[f"{component}_reason"]) > 0
