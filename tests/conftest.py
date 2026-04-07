"""Shared test fixtures for the property search tool."""

import pytest


@pytest.fixture
def base_config():
    """Return a minimal configuration matching production search_config.yaml structure."""
    return {
        "user": {
            "annual_income": 42256,
            "monthly_take_home": 2650,
            "total_savings": 37500,
            "deposit": 37500,
            "mortgage_rate": 4.5,
            "mortgage_term_years": 30,
        },
        "budget": {
            "freehold": {"ideal_min": 160000, "search_max": 210000},
            "leasehold": {"ideal_min": 130000, "search_max": 210000},
        },
        "monthly_target": {"min": 795, "recommended": 874, "max": 954},
        "all_in_monthly_max": 1200,
        "estimated_bills": {"total_monthly": 198},
        "living_costs": {"total_monthly": 340, "savings_target_monthly": 350},
        "council_tax_estimates": {
            "A": {"annual": 1123, "monthly": 94},
            "B": {"annual": 1310, "monthly": 109},
            "C": {"annual": 1497, "monthly": 125},
            "D": {"annual": 1683, "monthly": 140},
        },
        "hard_gates": {
            "min_bedrooms": 1,
            "lease_minimum_years": 120,
            "lease_absolute_minimum_years": 80,
            "sof_lease_minimum_years": 80,
            "service_charge_max_pa": 1800,
            "ground_rent_max_pa": 350,
            "council_tax_max_band": "C",
            "epc_minimum_rating": "C",
            "station_max_walk_min": 25,
            "supermarket_max_walk_min": 30,
            "flood_zone_reject": 3,
        },
        "crime_thresholds": {
            "asb_monthly_max": 10,
            "burglary_monthly_max": 3,
            "drugs_monthly_max": 3,
            "violent_monthly_max": 8,
        },
        "scoring": {
            "financial_fit": 30,
            "crime_safety": 25,
            "cost_predictability": 15,
            "layout_livability": 15,
            "walkability": 10,
            "long_term_flexibility": 5,
        },
        "keywords": {
            "reject_terms": ["in need of modernisation", "renovation project"],
            "doubling_clause_terms": ["doubling", "doubles every", "ground rent increases by 100%"],
        },
    }


@pytest.fixture
def freehold_property():
    """Return a basic freehold property that should pass all gates."""
    return {
        "id": 1,
        "price": 175000,
        "bedrooms": 2,
        "tenure": "freehold",
        "address": "1 Test Road, Tunbridge Wells",
        "postcode": "TN1 1AA",
        "council_tax_band": "B",
        "epc_rating": "C",
        "description": "A lovely 2 bedroom house in a quiet street.",
        "key_features": '["Garden", "Parking"]',
        "property_type": "Semi-detached",
    }


@pytest.fixture
def leasehold_property():
    """Return a basic leasehold property."""
    return {
        "id": 2,
        "price": 165000,
        "bedrooms": 2,
        "tenure": "leasehold",
        "lease_years": 125,
        "service_charge_pa": 1200,
        "ground_rent_pa": 200,
        "address": "Flat 1, Test Court",
        "postcode": "TN2 2BB",
        "council_tax_band": "A",
        "epc_rating": "B",
        "description": "A modern 2 bedroom flat with communal gardens.",
        "key_features": '["Parking", "Communal garden"]',
        "property_type": "Flat",
    }


@pytest.fixture
def basic_enrichment():
    """Return basic enrichment data that passes all enrichment gates."""
    return {
        "nearest_station_walk_min": 10,
        "nearest_supermarket_walk_min": 15,
        "crime_safety_score": 0.7,
        "crime_summary": '{"anti_social_behaviour": 5, "burglary": 1, "drugs": 1, "violent_crime": 3}',
        "flood_zone": 1,
    }
