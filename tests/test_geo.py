"""Tests for geographic utility functions — haversine edge cases."""

import math
import pytest
from src.utils.geo import haversine_miles, haversine_metres


class TestHaversineMiles:
    """Test great-circle distance in miles."""

    def test_same_point_returns_zero(self):
        assert haversine_miles(51.5, -0.1, 51.5, -0.1) == 0.0

    def test_known_distance_london_to_paris(self):
        # London (51.5074°N, 0.1278°W) to Paris (48.8566°N, 2.3522°E)
        distance = haversine_miles(51.5074, -0.1278, 48.8566, 2.3522)
        assert 200 < distance < 220  # ~213 miles

    def test_short_distance_tunbridge_wells_to_maidstone(self):
        # TW (51.132°N, 0.263°E) to Maidstone (51.272°N, 0.522°E)
        distance = haversine_miles(51.132, 0.263, 51.272, 0.522)
        assert 10 < distance < 15

    def test_antipodal_points(self):
        """Edge case: points on opposite sides of the globe."""
        distance = haversine_miles(0, 0, 0, 180)
        # Half circumference ≈ 12,450 miles
        assert 12000 < distance < 13000

    def test_nearly_identical_points_no_domain_error(self):
        """Phase 1 fix: floating-point should not cause math.asin domain error."""
        d = haversine_miles(51.13200001, 0.26300001, 51.13200002, 0.26300002)
        assert d >= 0
        assert d < 0.1  # Very close

    def test_negative_coordinates(self):
        distance = haversine_miles(-33.8688, 151.2093, -37.8136, 144.9631)  # Sydney to Melbourne
        assert 400 < distance < 500


class TestHaversineMetres:
    """Test great-circle distance in metres."""

    def test_same_point_returns_zero(self):
        assert haversine_metres(51.5, -0.1, 51.5, -0.1) == 0.0

    def test_short_distance(self):
        # Two points ~1km apart
        d = haversine_metres(51.5, -0.1, 51.509, -0.1)
        assert 900 < d < 1100

    def test_consistent_with_miles(self):
        lat1, lng1, lat2, lng2 = 51.132, 0.263, 51.272, 0.522
        miles = haversine_miles(lat1, lng1, lat2, lng2)
        metres = haversine_metres(lat1, lng1, lat2, lng2)
        # 1 mile ≈ 1609 metres
        assert abs(metres - miles * 1609.34) < 500  # Within 500m tolerance
