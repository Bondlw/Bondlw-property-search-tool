"""Property enrichment from external APIs.

Fetches:
- Crime data (data.police.uk)
- Nearest Lidl/Aldi (Nominatim OSM)
- Station walk times (already in Rightmove PAGE_MODEL, stored at detail-fetch time)
- Commute times (config lookup by postcode district)
"""

import json
import logging
import math
import time
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

WALK_SPEED_MPS = 1.4        # ~3 mph
METRES_PER_DEGREE_LAT = 111_000
NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
POLICE_API_BASE = "https://data.police.uk/api"

MAJOR_SUPERMARKET_CHAINS = [
    "Lidl", "Aldi", "Tesco", "Sainsbury's", "Asda",
    "Morrisons", "Co-op", "Waitrose", "M&S Food",
]


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Approximate distance in metres between two lat/lng points."""
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return 2 * math.asin(math.sqrt(a)) * 6_371_000


def _walk_min(distance_m: float) -> int:
    return max(1, round(distance_m / WALK_SPEED_MPS / 60))


class EnrichmentService:
    """Fetch and store enrichment data for a property."""

    def __init__(self, config: dict):
        self.config = config
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "PropertySearchTool/1.0 (personal use)"

    def _get(self, url: str, params: dict = None, timeout: int = 12) -> dict | None:
        try:
            r = self.session.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            logger.debug(f"HTTP {r.status_code} from {url}")
        except Exception as e:
            logger.debug(f"Request failed for {url}: {e}")
        return None

    # ── Crime ──────────────────────────────────────────────────────────────

    def fetch_crime(self, lat: float, lng: float) -> dict | None:
        """
        Return a dict of monthly crime counts by category at this location.
        Uses the most recent available month from data.police.uk.
        """
        # Try last 3 months in reverse order
        from datetime import date
        now = date.today()
        months = []
        for i in range(1, 4):
            m = now.month - i
            y = now.year
            if m <= 0:
                m += 12
                y -= 1
            months.append(f"{y}-{m:02d}")

        for month in months:
            data = self._get(
                f"{POLICE_API_BASE}/crimes-at-location",
                params={"lat": lat, "lng": lng, "date": month},
            )
            if data is not None:
                counts = {}
                for crime in data:
                    cat = crime.get("category", "other")
                    counts[cat] = counts.get(cat, 0) + 1

                # Normalise to our summary categories
                summary = {
                    "asb": counts.get("anti-social-behaviour", 0),
                    "burglary": counts.get("burglary", 0),
                    "drugs": counts.get("drugs", 0),
                    "violent": counts.get("violent-crime", 0),
                    "vehicle": counts.get("vehicle-crime", 0),
                    "total": sum(counts.values()),
                    "month": month,
                }
                return summary

            time.sleep(0.5)

        return None

    # ── Supermarkets ────────────────────────────────────────────────────────

    def _find_nearest_shop(self, brand: str, lat: float, lng: float, radius_m: int = 5000) -> tuple[float, int] | None:
        """Return (distance_m, walk_min) or None."""
        # Search a bounding box slightly larger than radius
        delta = radius_m / METRES_PER_DEGREE_LAT * 1.2
        data = self._get(
            f"{NOMINATIM_BASE}/search",
            params={
                "q": brand,
                "format": "json",
                "limit": 10,
                "viewbox": f"{lng-delta},{lat+delta},{lng+delta},{lat-delta}",
                "bounded": 1,
            },
        )
        time.sleep(1.1)  # Nominatim rate limit: 1 req/s

        if not data:
            return None

        best_dist = None
        for item in data:
            try:
                slat, slng = float(item["lat"]), float(item["lon"])
                dist = _haversine_m(lat, lng, slat, slng)
                if best_dist is None or dist < best_dist:
                    best_dist = dist
            except (KeyError, ValueError):
                continue

        if best_dist is not None and best_dist <= radius_m:
            return best_dist, _walk_min(best_dist)
        return None

    def fetch_supermarkets(self, lat: float, lng: float) -> dict:
        """Return nearest major supermarket distances (any chain)."""
        result = {}
        best_dist = None
        best_name = None
        best_walk = None

        for chain in MAJOR_SUPERMARKET_CHAINS:
            found = self._find_nearest_shop(chain, lat, lng)

            # Store Lidl and Aldi individually for backwards compatibility
            if chain == "Lidl" and found:
                result["lidl_distance_m"] = round(found[0], 1)
                result["lidl_walk_min"] = found[1]
            elif chain == "Aldi" and found:
                result["aldi_distance_m"] = round(found[0], 1)
                result["aldi_walk_min"] = found[1]

            if found and (best_dist is None or found[0] < best_dist):
                best_dist = found[0]
                best_name = chain
                best_walk = found[1]

        if best_dist is not None:
            result["nearest_supermarket_name"] = best_name
            result["nearest_supermarket_distance_m"] = round(best_dist, 1)
            result["nearest_supermarket_walk_min"] = best_walk

        return result

    # ── Commute lookup ──────────────────────────────────────────────────────

    def lookup_commute(self, postcode: str, nearest_station: str | None = None) -> dict:
        """Look up commute times from the config table.

        Matches by nearest station name (preferred) or postcode district prefix.
        """
        commute_table = self.config.get("commute_lookup", {})
        if not commute_table:
            return {}

        entry = None

        # Try matching by nearest station name (fuzzy: check if config key is substring)
        if nearest_station:
            station_clean = nearest_station.replace(" Station", "").strip()
            for key, val in commute_table.items():
                if key.lower() in station_clean.lower() or station_clean.lower() in key.lower():
                    entry = val
                    break

        # Fallback: postcode district prefix lookup
        if not entry and postcode:
            district = postcode[:len(postcode) - 3].strip().upper() if len(postcode) >= 5 else postcode.upper()
            # Map known postcode districts to station names
            district_to_station = {
                "ME4": "Chatham", "ME5": "Chatham",
                "ME1": "Rochester", "ME2": "Strood", "ME7": "Gillingham (Kent)",
                "ME8": "Gillingham (Kent)", "ME3": "Rochester",
                "ME14": "Maidstone East", "ME15": "Maidstone East", "ME16": "Maidstone West",
                "DA1": "Dartford", "DA2": "Dartford", "DA11": "Gravesend",
                "TN23": "Ashford International", "TN24": "Ashford International",
                "ME10": "Sittingbourne", "ME9": "Sittingbourne",
                "ME13": "Faversham",
                "ME19": "West Malling", "ME20": "Aylesford",
                "ME6": "Snodland",
                "CT1": "Canterbury East", "CT2": "Canterbury East",
            }
            station_name = district_to_station.get(district)
            if station_name:
                entry = commute_table.get(station_name)

        if not entry:
            return {}

        return {
            "commute_to_london_min": entry.get("london_min"),
            "commute_to_maidstone_min": entry.get("maidstone_min"),
            "annual_season_ticket": entry.get("season_ticket"),
        }

    # ── Main enrichment entry point ─────────────────────────────────────────

    def enrich(self, prop: dict, existing_enrichment: dict | None = None) -> dict:
        """
        Fetch all available enrichment data for a property.
        Returns an enrichment dict ready to upsert into enrichment_data.

        existing_enrichment: any already-stored enrichment data for this property
        (e.g., station data stored during detail fetch).
        """
        lat = prop.get("latitude")
        lng = prop.get("longitude")
        postcode = prop.get("postcode", "")
        result = {"property_id": prop["id"]}

        # Carry forward existing enrichment fields
        nearest_station = None
        if existing_enrichment:
            nearest_station = existing_enrichment.get("nearest_station_name")

        if lat and lng:
            # Crime
            logger.debug(f"Fetching crime for {prop.get('address')} ({lat}, {lng})")
            crime = self.fetch_crime(lat, lng)
            if crime:
                result["crime_summary"] = json.dumps(crime)
                result["crime_data_date"] = crime.get("month")
                # Simple safety score: 100 - penalties
                total = crime.get("total", 0)
                score = max(0.0, 100.0 - total * 2)
                result["crime_safety_score"] = round(score, 1)

            # Supermarkets
            logger.debug(f"Fetching supermarkets for {prop.get('address')}")
            supers = self.fetch_supermarkets(lat, lng)
            if supers.get("lidl_distance_m"):
                result["nearest_lidl_distance_m"] = supers["lidl_distance_m"]
                result["nearest_lidl_walk_min"] = supers["lidl_walk_min"]
            if supers.get("aldi_distance_m"):
                result["nearest_aldi_distance_m"] = supers["aldi_distance_m"]
                result["nearest_aldi_walk_min"] = supers["aldi_walk_min"]
            if supers.get("nearest_supermarket_name"):
                result["nearest_supermarket_name"] = supers["nearest_supermarket_name"]
                result["nearest_supermarket_distance_m"] = supers["nearest_supermarket_distance_m"]
                result["nearest_supermarket_walk_min"] = supers["nearest_supermarket_walk_min"]

        # Commute lookup (uses station name or postcode district, no API call)
        commute = self.lookup_commute(postcode, nearest_station)
        result.update(commute)

        result["enriched_at"] = datetime.now().isoformat()
        return result
