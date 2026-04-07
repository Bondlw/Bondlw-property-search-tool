"""Tests for hard gate checks — each gate pass/fail scenario."""

import pytest
from src.filtering.hard_gates import (
    check_all_gates,
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
    check_station_walkable,
    check_supermarket_walkable,
    check_crime_safety,
    check_flood_risk,
)


class TestPriceCap:
    """Test dynamic price cap gate."""

    def test_affordable_freehold_passes(self, freehold_property, base_config):
        result = check_price_cap(freehold_property, None, base_config)
        assert result.passed is True

    def test_expensive_property_fails(self, freehold_property, base_config):
        freehold_property["price"] = 300000
        result = check_price_cap(freehold_property, None, base_config)
        assert result.passed is False
        assert "exceeds" in result.reason

    def test_unknown_tenure_fails(self, freehold_property, base_config):
        del freehold_property["tenure"]
        result = check_price_cap(freehold_property, None, base_config)
        assert result.passed is False
        assert "unknown" in result.reason.lower()

    def test_below_floor_fails(self, freehold_property, base_config):
        freehold_property["price"] = 100000
        result = check_price_cap(freehold_property, None, base_config)
        assert result.passed is False
        assert "below minimum" in result.reason

    def test_extreme_service_charge_negative_cap(self, base_config, leasehold_property):
        """Phase 1 fix: extreme SC should give clear error, not negative cap."""
        leasehold_property["service_charge_pa"] = 20000
        result = check_price_cap(leasehold_property, None, base_config)
        assert result.passed is False
        assert "Cannot afford" in result.reason or "exceeds" in result.reason


class TestMonthlyCost:
    """Test monthly cost ceiling gate."""

    def test_affordable_passes(self, freehold_property, base_config):
        freehold_property["price"] = 160000
        result = check_monthly_cost(freehold_property, None, base_config)
        assert result.passed is True

    def test_expensive_monthly_fails(self, freehold_property, base_config):
        freehold_property["price"] = 250000
        result = check_monthly_cost(freehold_property, None, base_config)
        assert result.passed is False
        assert "exceeds" in result.reason


class TestMinBedrooms:
    """Test bedroom count gate."""

    def test_enough_bedrooms_passes(self, freehold_property, base_config):
        result = check_min_bedrooms(freehold_property, None, base_config)
        assert result.passed is True

    def test_zero_bedrooms_fails(self, freehold_property, base_config):
        freehold_property["bedrooms"] = 0
        result = check_min_bedrooms(freehold_property, None, base_config)
        assert result.passed is False

    def test_unknown_bedrooms_fails(self, freehold_property, base_config):
        freehold_property["bedrooms"] = None
        result = check_min_bedrooms(freehold_property, None, base_config)
        assert result.passed is False


class TestSeparateLounge:
    """Test studio/bedsit rejection."""

    def test_normal_property_passes(self, freehold_property, base_config):
        result = check_separate_lounge(freehold_property, None, base_config)
        assert result.passed is True

    def test_studio_fails(self, freehold_property, base_config):
        freehold_property["property_type"] = "Studio"
        result = check_separate_lounge(freehold_property, None, base_config)
        assert result.passed is False

    def test_bedsit_fails(self, freehold_property, base_config):
        freehold_property["description"] = "A lovely bedsit in the town centre"
        result = check_separate_lounge(freehold_property, None, base_config)
        assert result.passed is False


class TestMoveInReady:
    """Test renovation/cash-only rejection."""

    def test_ready_property_passes(self, freehold_property, base_config):
        result = check_move_in_ready(freehold_property, None, base_config)
        assert result.passed is True

    def test_renovation_project_fails(self, freehold_property, base_config):
        freehold_property["description"] = "An exciting renovation project"
        result = check_move_in_ready(freehold_property, None, base_config)
        # Only fails if "renovation" is in reject_terms — depends on config
        # Our config has "in need of modernisation" and "renovation project"
        assert result.passed is False

    def test_cash_only_fails(self, freehold_property, base_config):
        freehold_property["description"] = "Cash buyers only. Priced for quick sale."
        result = check_move_in_ready(freehold_property, None, base_config)
        assert result.passed is False

    def test_investor_friendly_passes(self, freehold_property, base_config):
        """'Investor' alone is NOT a rejection — agents routinely say it."""
        freehold_property["description"] = "Suitable for investors or first time buyers."
        result = check_move_in_ready(freehold_property, None, base_config)
        assert result.passed is True


class TestNotRetirement:
    """Test retirement property rejection."""

    def test_normal_passes(self, freehold_property, base_config):
        result = check_not_retirement(freehold_property, None, base_config)
        assert result.passed is True

    def test_retirement_fails(self, freehold_property, base_config):
        freehold_property["description"] = "A retirement complex for over 55s"
        result = check_not_retirement(freehold_property, None, base_config)
        assert result.passed is False


class TestNotAuction:
    """Test auction rejection (guide price is OK)."""

    def test_normal_passes(self, freehold_property, base_config):
        result = check_not_auction(freehold_property, None, base_config)
        assert result.passed is True

    def test_auction_status_fails(self, freehold_property, base_config):
        freehold_property["status"] = "Auction"
        result = check_not_auction(freehold_property, None, base_config)
        assert result.passed is False

    def test_auction_context_fails(self, freehold_property, base_config):
        freehold_property["description"] = "This property is offered at auction on 15th March."
        result = check_not_auction(freehold_property, None, base_config)
        assert result.passed is False


class TestNotNonStandard:
    """Test non-standard dwelling rejection."""

    def test_normal_passes(self, freehold_property, base_config):
        result = check_not_non_standard(freehold_property, None, base_config)
        assert result.passed is True

    def test_houseboat_fails(self, freehold_property, base_config):
        freehold_property["property_type"] = "Houseboat"
        result = check_not_non_standard(freehold_property, None, base_config)
        assert result.passed is False

    def test_park_home_fails(self, freehold_property, base_config):
        freehold_property["title"] = "Park home on lovely site"
        result = check_not_non_standard(freehold_property, None, base_config)
        assert result.passed is False


class TestLeaseLength:
    """Test lease length gate — complex logic with extension cost check."""

    def test_freehold_passes(self, freehold_property, base_config):
        result = check_lease_length(freehold_property, None, base_config)
        assert result.passed is True
        assert "Freehold" in result.reason

    def test_long_lease_passes(self, leasehold_property, base_config):
        leasehold_property["lease_years"] = 125
        result = check_lease_length(leasehold_property, None, base_config)
        assert result.passed is True

    def test_short_lease_below_absolute_min_fails(self, leasehold_property, base_config):
        leasehold_property["lease_years"] = 70
        result = check_lease_length(leasehold_property, None, base_config)
        assert result.passed is False
        assert "hard minimum" in result.reason

    def test_unknown_lease_needs_verification(self, leasehold_property, base_config):
        leasehold_property["lease_years"] = None
        result = check_lease_length(leasehold_property, None, base_config)
        assert result.needs_verification is True

    def test_sof_lease_passes_lower_minimum(self, base_config):
        prop = {
            "price": 165000,
            "bedrooms": 2,
            "tenure": "share_of_freehold",
            "lease_years": 85,
            "service_charge_pa": 1000,
            "ground_rent_pa": 0,
        }
        result = check_lease_length(prop, None, base_config)
        assert result.passed is True
        assert "SOF" in result.reason


class TestServiceCharge:
    """Test service charge cap gate."""

    def test_freehold_passes(self, freehold_property, base_config):
        result = check_service_charge(freehold_property, None, base_config)
        assert result.passed is True

    def test_within_cap_passes(self, leasehold_property, base_config):
        leasehold_property["service_charge_pa"] = 1200
        result = check_service_charge(leasehold_property, None, base_config)
        assert result.passed is True

    def test_over_cap_fails(self, leasehold_property, base_config):
        leasehold_property["service_charge_pa"] = 2500
        result = check_service_charge(leasehold_property, None, base_config)
        assert result.passed is False

    def test_unknown_needs_verification(self, leasehold_property, base_config):
        leasehold_property["service_charge_pa"] = None
        result = check_service_charge(leasehold_property, None, base_config)
        assert result.needs_verification is True


class TestGroundRent:
    """Test ground rent cap gate."""

    def test_freehold_passes(self, freehold_property, base_config):
        result = check_ground_rent(freehold_property, None, base_config)
        assert result.passed is True

    def test_within_cap_passes(self, leasehold_property, base_config):
        leasehold_property["ground_rent_pa"] = 200
        result = check_ground_rent(leasehold_property, None, base_config)
        assert result.passed is True

    def test_over_cap_within_tolerance_flags(self, leasehold_property, base_config):
        leasehold_property["ground_rent_pa"] = 500
        result = check_ground_rent(leasehold_property, None, base_config)
        assert result.passed is True
        assert result.needs_verification is True

    def test_over_cap_beyond_tolerance_fails(self, leasehold_property, base_config):
        leasehold_property["ground_rent_pa"] = 1000
        result = check_ground_rent(leasehold_property, None, base_config)
        assert result.passed is False


class TestDoublingClause:
    """Test ground rent doubling clause detection."""

    def test_no_clause_passes(self, leasehold_property, base_config):
        result = check_no_doubling_clause(leasehold_property, None, base_config)
        assert result.passed is True

    def test_doubling_clause_fails(self, leasehold_property, base_config):
        leasehold_property["description"] = "Ground rent doubles every 25 years."
        result = check_no_doubling_clause(leasehold_property, None, base_config)
        assert result.passed is False


class TestCouncilTaxBand:
    """Test council tax band gate."""

    def test_band_within_cap_passes(self, freehold_property, base_config):
        freehold_property["council_tax_band"] = "B"
        result = check_council_tax_band(freehold_property, None, base_config)
        assert result.passed is True

    def test_band_over_cap_fails(self, freehold_property, base_config):
        freehold_property["council_tax_band"] = "F"
        result = check_council_tax_band(freehold_property, None, base_config)
        assert result.passed is False


class TestEpcRating:
    """Test EPC rating gate."""

    def test_good_rating_passes(self, freehold_property, base_config):
        freehold_property["epc_rating"] = "B"
        result = check_epc_rating(freehold_property, None, base_config)
        assert result.passed is True

    def test_poor_rating_fails(self, freehold_property, base_config):
        freehold_property["epc_rating"] = "F"
        result = check_epc_rating(freehold_property, None, base_config)
        assert result.passed is False


class TestAllGates:
    """Integration test — run all gates together."""

    def test_qualifying_freehold_passes_all(self, freehold_property, basic_enrichment, base_config):
        all_passed, results = check_all_gates(freehold_property, basic_enrichment, base_config)
        failed = [r for r in results if not r.passed]
        assert all_passed, f"Failed gates: {[(r.gate_name, r.reason) for r in failed]}"

    def test_expensive_property_fails_price_gate(self, freehold_property, basic_enrichment, base_config):
        freehold_property["price"] = 300000
        all_passed, results = check_all_gates(freehold_property, basic_enrichment, base_config)
        assert not all_passed
        failed_names = {r.gate_name for r in results if not r.passed}
        assert "price_cap" in failed_names or "monthly_cost" in failed_names

    def test_no_enrichment_skips_enrichment_gates(self, freehold_property, base_config):
        all_passed, results = check_all_gates(freehold_property, None, base_config)
        gate_names = {r.gate_name for r in results}
        # Station, supermarket, crime, flood gates should NOT be in results
        assert "station_walkable" not in gate_names
        assert "crime_safety" not in gate_names


class TestStationWalkable:
    """Test station walk distance gate."""

    def test_close_station_passes(self, freehold_property, basic_enrichment, base_config):
        basic_enrichment["nearest_station_walk_min"] = 10
        result = check_station_walkable(freehold_property, basic_enrichment, base_config)
        assert result.passed is True

    def test_far_station_fails(self, freehold_property, basic_enrichment, base_config):
        basic_enrichment["nearest_station_walk_min"] = 35
        result = check_station_walkable(freehold_property, basic_enrichment, base_config)
        assert result.passed is False

    def test_no_enrichment_fails(self, freehold_property, base_config):
        result = check_station_walkable(freehold_property, None, base_config)
        assert result.passed is False

    def test_no_station_data_fails(self, freehold_property, base_config):
        result = check_station_walkable(freehold_property, {}, base_config)
        assert result.passed is False


class TestSupermarketWalkable:
    """Test supermarket walk distance gate."""

    def test_close_supermarket_passes(self, freehold_property, basic_enrichment, base_config):
        result = check_supermarket_walkable(freehold_property, basic_enrichment, base_config)
        assert result.passed is True

    def test_far_supermarket_fails(self, freehold_property, base_config):
        enrichment = {"nearest_supermarket_walk_min": 40, "nearest_supermarket_name": "Tesco"}
        result = check_supermarket_walkable(freehold_property, enrichment, base_config)
        assert result.passed is False

    def test_fallback_to_lidl(self, freehold_property, base_config):
        enrichment = {"nearest_lidl_walk_min": 10}
        result = check_supermarket_walkable(freehold_property, enrichment, base_config)
        assert result.passed is True

    def test_no_supermarket_data(self, freehold_property, base_config):
        result = check_supermarket_walkable(freehold_property, {}, base_config)
        assert result.passed is False


class TestCrimeSafetyGate:
    """Test crime safety gate (different from crime scoring)."""

    def test_low_crime_passes(self, freehold_property, base_config):
        enrichment = {"crime_summary": '{"asb": 3, "burglary": 1, "drugs": 1, "violent": 3}'}
        result = check_crime_safety(freehold_property, enrichment, base_config)
        assert result.passed is True

    def test_high_crime_fails(self, freehold_property, base_config):
        enrichment = {"crime_summary": '{"asb": 20, "burglary": 10, "drugs": 10, "violent": 20}'}
        result = check_crime_safety(freehold_property, enrichment, base_config)
        assert result.passed is False

    def test_no_enrichment_fails(self, freehold_property, base_config):
        result = check_crime_safety(freehold_property, None, base_config)
        assert result.passed is False

    def test_invalid_json_fails(self, freehold_property, base_config):
        result = check_crime_safety(freehold_property, {"crime_summary": "not json"}, base_config)
        assert result.passed is False

    def test_no_crime_data_fails(self, freehold_property, base_config):
        result = check_crime_safety(freehold_property, {}, base_config)
        assert result.passed is False


class TestFloodRisk:
    """Test flood risk gate."""

    def test_zone_1_passes(self, freehold_property, base_config):
        result = check_flood_risk(freehold_property, {"flood_zone": 1}, base_config)
        assert result.passed is True

    def test_zone_3_fails(self, freehold_property, base_config):
        result = check_flood_risk(freehold_property, {"flood_zone": 3}, base_config)
        assert result.passed is False

    def test_no_flood_data_passes(self, freehold_property, base_config):
        """No flood data should not reject — it's supplementary."""
        result = check_flood_risk(freehold_property, {"flood_zone": None}, base_config)
        assert result.passed is True

    def test_no_enrichment_fails(self, freehold_property, base_config):
        result = check_flood_risk(freehold_property, None, base_config)
        assert result.passed is False


class TestNoTbcFields:
    """Test TBC fields gate for leaseholds."""

    def test_freehold_passes(self, freehold_property, base_config):
        result = check_no_tbc_fields(freehold_property, None, base_config)
        assert result.passed is True

    def test_leasehold_all_known_passes(self, leasehold_property, base_config):
        result = check_no_tbc_fields(leasehold_property, None, base_config)
        assert result.passed is True

    def test_leasehold_tbc_in_description_needs_verification(self, leasehold_property, base_config):
        leasehold_property["description"] = "service charge tbc, ground rent included"
        result = check_no_tbc_fields(leasehold_property, None, base_config)
        assert result.passed is True
        assert result.needs_verification is True
