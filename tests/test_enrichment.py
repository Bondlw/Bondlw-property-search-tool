"""Tests for the enrichment service — crime, supermarkets, and commute lookup."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.enrichment.enrichment_service import EnrichmentService, _walk_min


@pytest.fixture
def enrichment_config():
    return {
        "commute_lookup": {
            "Chatham": {"london_min": 50, "maidstone_min": 20, "season_ticket": 3500},
            "Rochester": {"london_min": 45, "maidstone_min": 25, "season_ticket": 3200},
            "Maidstone East": {"london_min": 60, "maidstone_min": 5, "season_ticket": 4000},
        },
    }


@pytest.fixture
def service(enrichment_config):
    return EnrichmentService(enrichment_config)


# ── _walk_min ──────────────────────────────────────────────────────────────

class TestWalkMin:
    def test_minimum_one_minute(self):
        assert _walk_min(0) == 1
        assert _walk_min(10) == 1

    def test_reasonable_distance(self):
        # 840m at 1.4 m/s = 600s = 10 min
        assert _walk_min(840) == 10

    def test_large_distance(self):
        # 2100m at 1.4 m/s = 1500s = 25 min
        assert _walk_min(2100) == 25


# ── Commute lookup ────────────────────────────────────────────────────────

class TestLookupCommute:
    def test_matches_by_station_name(self, service):
        result = service.lookup_commute("ME4 6AA", nearest_station="Chatham")
        assert result["commute_to_london_min"] == 50
        assert result["commute_to_maidstone_min"] == 20
        assert result["annual_season_ticket"] == 3500

    def test_matches_by_station_with_suffix(self, service):
        result = service.lookup_commute("ME4 6AA", nearest_station="Chatham Station")
        assert result["commute_to_london_min"] == 50

    def test_falls_back_to_postcode_district(self, service):
        result = service.lookup_commute("ME4 6AA")
        assert result["commute_to_london_min"] == 50

    def test_maidstone_postcode(self, service):
        result = service.lookup_commute("ME14 1AA")
        assert result["commute_to_maidstone_min"] == 5

    def test_unknown_postcode_returns_empty(self, service):
        result = service.lookup_commute("SW1A 1AA")
        assert result == {}

    def test_no_commute_table_returns_empty(self):
        service = EnrichmentService({})
        result = service.lookup_commute("ME4 6AA", nearest_station="Chatham")
        assert result == {}


# ── fetch_crime ───────────────────────────────────────────────────────────

class TestFetchCrime:
    def test_parses_crime_response(self, service):
        mock_crimes = [
            {"category": "anti-social-behaviour"},
            {"category": "anti-social-behaviour"},
            {"category": "burglary"},
            {"category": "violent-crime"},
            {"category": "drugs"},
            {"category": "vehicle-crime"},
        ]
        with patch.object(service, "_get", return_value=mock_crimes):
            result = service.fetch_crime(51.37, 0.53)
        assert result is not None
        assert result["asb"] == 2
        assert result["burglary"] == 1
        assert result["violent"] == 1
        assert result["drugs"] == 1
        assert result["vehicle"] == 1
        assert result["total"] == 6

    def test_returns_none_when_all_months_fail(self, service):
        with patch.object(service, "_get", return_value=None):
            result = service.fetch_crime(51.37, 0.53)
        assert result is None

    def test_tries_multiple_months(self, service):
        call_count = 0
        def mock_get(url, params=None):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return None
            return [{"category": "burglary"}]

        with patch.object(service, "_get", side_effect=mock_get):
            with patch("src.enrichment.enrichment_service.time.sleep"):
                result = service.fetch_crime(51.37, 0.53)
        assert result is not None
        assert result["burglary"] == 1
        assert call_count == 3


# ── fetch_supermarkets ────────────────────────────────────────────────────

class TestFetchSupermarkets:
    def test_finds_nearest_supermarket(self, service):
        """Mock Nominatim to return Lidl/Aldi results."""
        def mock_find_nearest(brand, lat, lng, radius_m=5000):
            distances = {"Lidl": (800, 10), "Aldi": (1200, 14)}
            return distances.get(brand)

        with patch.object(service, "_find_nearest_shop", side_effect=mock_find_nearest):
            result = service.fetch_supermarkets(51.37, 0.53)

        assert result["nearest_lidl_distance_m"] == 800
        assert result["nearest_lidl_walk_min"] == 10
        assert result["nearest_aldi_distance_m"] == 1200
        assert result["nearest_aldi_walk_min"] == 14
        assert result["nearest_supermarket_name"] == "Lidl"

    def test_no_supermarkets_found(self, service):
        with patch.object(service, "_find_nearest_shop", return_value=None):
            result = service.fetch_supermarkets(51.37, 0.53)
        assert "nearest_supermarket_name" not in result
        assert "nearest_lidl_distance_m" not in result


# ── enrich (main entry point) ─────────────────────────────────────────────

class TestEnrich:
    def test_enriches_property(self, service):
        prop = {"id": 1, "latitude": 51.37, "longitude": 0.53, "postcode": "ME4 6AA", "address": "Test"}
        crime_mock = {"asb": 2, "burglary": 1, "drugs": 0, "violent": 1, "vehicle": 0, "total": 4, "month": "2026-02"}
        super_mock = {"nearest_lidl_distance_m": 900, "nearest_supermarket_name": "Lidl", "nearest_supermarket_distance_m": 900, "nearest_supermarket_walk_min": 11}

        with patch.object(service, "fetch_crime", return_value=crime_mock):
            with patch.object(service, "fetch_supermarkets", return_value=super_mock):
                result = service.enrich(prop)

        assert result["property_id"] == 1
        assert "crime_summary" in result
        assert result["crime_safety_score"] == 92.0  # 100 - 4*2
        assert result["nearest_supermarket_name"] == "Lidl"
        assert result["commute_to_london_min"] == 50
        assert "enriched_at" in result

    def test_skips_crime_if_already_populated(self, service):
        prop = {"id": 1, "latitude": 51.37, "longitude": 0.53, "postcode": "ME4 6AA"}
        existing = {"crime_summary": '{"total": 5}'}

        with patch.object(service, "fetch_crime") as mock_crime:
            with patch.object(service, "fetch_supermarkets", return_value={}):
                service.enrich(prop, existing_enrichment=existing)

        mock_crime.assert_not_called()

    def test_skips_supermarkets_if_already_populated(self, service):
        prop = {"id": 1, "latitude": 51.37, "longitude": 0.53, "postcode": "ME4 6AA"}
        existing = {"nearest_supermarket_name": "Lidl"}

        with patch.object(service, "fetch_crime", return_value=None):
            with patch.object(service, "fetch_supermarkets") as mock_super:
                service.enrich(prop, existing_enrichment=existing)

        mock_super.assert_not_called()

    def test_handles_no_coordinates(self, service):
        prop = {"id": 1, "latitude": None, "longitude": None, "postcode": "ME4 6AA"}
        result = service.enrich(prop)
        assert "crime_summary" not in result
        assert result["commute_to_london_min"] == 50

    def test_validates_crime_data_numeric(self, service):
        """Non-numeric crime values should be skipped."""
        prop = {"id": 1, "latitude": 51.37, "longitude": 0.53, "postcode": "ME4 6AA"}
        bad_crime = {"asb": "many", "burglary": 1, "drugs": 0, "violent": 0, "vehicle": 0, "total": 1, "month": "2026-02"}

        with patch.object(service, "fetch_crime", return_value=bad_crime):
            with patch.object(service, "fetch_supermarkets", return_value={}):
                result = service.enrich(prop)

        assert "crime_summary" not in result
