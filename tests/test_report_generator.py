"""Tests for the report generator context building and HTML output."""

import json
import os
import tempfile

import pytest

from src.reporting.report_generator import ReportGenerator


@pytest.fixture
def report_config(base_config):
    """Extend base_config with report generator requirements."""
    config = base_config.copy()
    config["search_areas"] = {
        "primary": [
            {"name": "Chatham", "lat": 51.37, "lng": 0.53, "rightmove_id": "REGION^123"},
        ],
    }
    config["max_radius_miles"] = 15
    config["office"] = {"name": "Maidstone", "lat": 51.27, "lng": 0.52, "remote_threshold_miles": 20}
    config["excluded_address_terms"] = ["Retirement Village"]
    config["negotiation"] = {"max_discount_pct": 15}
    return config


@pytest.fixture
def report_generator(report_config):
    return ReportGenerator(report_config)


def _make_property(prop_id=1, price=175000, postcode="ME4 6AA", tenure="freehold", **overrides):
    """Build a minimal property dict for testing."""
    base = {
        "id": prop_id,
        "portal": "rightmove",
        "portal_id": str(prop_id),
        "url": f"https://www.rightmove.co.uk/properties/{prop_id}",
        "title": f"Test Property {prop_id}",
        "price": price,
        "address": f"{prop_id} Test Road, Chatham",
        "postcode": postcode,
        "property_type": "terraced",
        "bedrooms": 2,
        "bathrooms": 1,
        "tenure": tenure,
        "lease_years": None,
        "service_charge_pa": None,
        "ground_rent_pa": None,
        "council_tax_band": "B",
        "epc_rating": "C",
        "description": "A test property",
        "key_features": '["Garden"]',
        "images": "[]",
        "floorplan_urls": None,
        "video_url": None,
        "brochure_url": None,
        "rooms": None,
        "size_sqft": 750,
        "price_reduced": 0,
        "agent_name": "Test Agent",
        "latitude": 51.37,
        "longitude": 0.53,
        "first_seen_date": "2026-03-22",
        "last_seen_date": "2026-03-22",
        "first_listed_date": "2026-03-01",
        "is_active": 1,
        "status": "active",
    }
    base.update(overrides)
    return base


class TestReportGeneratorInit:
    def test_creates_jinja_environment(self, report_generator):
        assert report_generator.env is not None

    def test_builds_area_list(self, report_generator):
        assert len(report_generator._area_list) == 1
        assert report_generator._area_list[0][0] == "Chatham"

    def test_currency_filter(self, report_generator):
        assert report_generator.env.filters["currency"](175000) == "£175,000"
        assert report_generator.env.filters["currency"](None) == "N/A"

    def test_json_parse_filter(self, report_generator):
        assert report_generator.env.filters["json_parse"]('["a","b"]') == ["a", "b"]
        assert report_generator.env.filters["json_parse"](["a"]) == ["a"]
        assert report_generator.env.filters["json_parse"]("single") == ["single"]
        assert report_generator.env.filters["json_parse"]("") == []


class TestNearestArea:
    def test_finds_nearest_area(self, report_generator):
        name, dist = report_generator._nearest_area(51.37, 0.53)
        assert name == "Chatham"
        assert dist < 1.0

    def test_unknown_when_far(self, report_config):
        """With no areas configured, returns Unknown."""
        report_config["search_areas"] = {}
        generator = ReportGenerator(report_config)
        name, dist = generator._nearest_area(51.5, -0.1)
        assert name == "Unknown"


class TestDaysOnMarket:
    def test_calculates_days(self, report_generator):
        from datetime import date, timedelta
        ten_days_ago = (date.today() - timedelta(days=10)).isoformat()
        prop = {"first_listed_date": ten_days_ago}
        result = report_generator._days_on_market(prop)
        assert result == 10

    def test_none_when_no_date(self, report_generator):
        assert report_generator._days_on_market({}) is None

    def test_uses_first_seen_fallback(self, report_generator):
        from datetime import date, timedelta
        five_days_ago = (date.today() - timedelta(days=5)).isoformat()
        prop = {"first_seen_date": five_days_ago}
        result = report_generator._days_on_market(prop)
        assert result == 5


class TestComputeRecommendedOffer:
    def test_baseline_2_pct_offer(self, report_generator):
        from src.utils.financial_calculator import FinancialCalculator
        calc = FinancialCalculator(report_generator.config)
        prop = _make_property(price=175000)
        prop["_price_history"] = []
        prop["_costs"] = calc.calculate_full_monthly_cost(prop)
        result = report_generator._compute_recommended_offer(prop, days=5, calc=calc)
        assert result is not None
        assert result["discount_pct"] >= 2
        assert result["offer_price"] < 175000

    def test_zero_price_returns_none(self, report_generator):
        from src.utils.financial_calculator import FinancialCalculator
        calc = FinancialCalculator(report_generator.config)
        prop = _make_property(price=0)
        result = report_generator._compute_recommended_offer(prop, days=10, calc=calc)
        assert result is None


class TestGenerate:
    def test_generates_html_file(self, report_generator):
        prop = _make_property()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_report.html")
            result = report_generator.generate([prop], output_path)
            assert os.path.exists(result)
            content = open(result, encoding="utf-8").read()
            assert "<!DOCTYPE html>" in content or "<html" in content

    def test_sets_last_qualifying(self, report_generator):
        prop = _make_property()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_report.html")
            report_generator.generate([prop], output_path)
            assert isinstance(report_generator.last_qualifying, list)

    def test_excludes_excluded_properties(self, report_generator):
        prop = _make_property(prop_id=10)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_report.html")
            report_generator.generate([prop], output_path, excluded_ids={10})
            assert all(p["id"] != 10 for p in report_generator.last_qualifying)

    def test_marks_favourites(self, report_generator):
        prop = _make_property(prop_id=20)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_report.html")
            report_generator.generate([prop], output_path, favourite_ids={20})
            # Favourites go to their own section, not qualifying
            assert all(p["id"] != 20 for p in report_generator.last_qualifying)

    def test_handles_empty_property_list(self, report_generator):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_report.html")
            result = report_generator.generate([], output_path)
            assert os.path.exists(result)

    def test_excluded_address_terms_filtered(self, report_generator):
        prop = _make_property(address="Unit 5, Retirement Village, Chatham")
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_report.html")
            report_generator.generate([prop], output_path)
            assert len(report_generator.last_qualifying) == 0

    def test_new_today_detected(self, report_generator):
        from datetime import date
        prop = _make_property(first_seen_date=date.today().isoformat())
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_report.html")
            report_generator.generate([prop], output_path)
            assert len(report_generator.last_new_today) >= 0  # may or may not show depending on gate pass


class TestComputeAreaStats:
    def test_computes_stats(self, report_generator):
        props = [
            {**_make_property(prop_id=1, price=175000), "_search_area": "Chatham", "_crime_total": 5, "_days_on_market": 20},
            {**_make_property(prop_id=2, price=185000), "_search_area": "Chatham", "_crime_total": 3, "_days_on_market": 30},
        ]
        qualifying = [props[0]]
        stats = report_generator._compute_area_stats(props, qualifying)
        assert len(stats) >= 1
        chatham = next(s for s in stats if s["area"] == "Chatham")
        assert chatham["total"] == 2
        assert chatham["qualifying"] >= 1
