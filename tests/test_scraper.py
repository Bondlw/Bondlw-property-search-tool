"""Tests for the Rightmove scraper HTML parsing and data extraction.

Tests pure parsing/extraction logic — no HTTP calls.
"""

import json
import pytest

from src.scrapers.rightmove_scraper import RightmoveScraper
from src.scrapers.http_client import HttpClient


@pytest.fixture
def scraper():
    """Create a scraper with a dummy HTTP client (won't be used in unit tests)."""
    client = HttpClient.__new__(HttpClient)
    client.session = None
    return RightmoveScraper(client)


# ── _normalise_property_type ───────────────────────────────────────────────

class TestNormalisePropertyType:
    def test_flat_variants(self, scraper):
        assert scraper._normalise_property_type("flat") == "flat"
        assert scraper._normalise_property_type("Apartment") == "flat"
        assert scraper._normalise_property_type("maisonette") == "flat"
        assert scraper._normalise_property_type("Ground Floor Flat") == "flat"

    def test_house_types(self, scraper):
        assert scraper._normalise_property_type("semi-detached") == "semi-detached"
        assert scraper._normalise_property_type("detached") == "detached"
        assert scraper._normalise_property_type("terraced") == "terraced"

    def test_other_types(self, scraper):
        assert scraper._normalise_property_type("bungalow") == "bungalow"
        assert scraper._normalise_property_type("cottage") == "cottage"
        assert scraper._normalise_property_type("end of terrace") == "terraced"

    def test_unknown_type(self, scraper):
        assert scraper._normalise_property_type("castle") == "castle"
        assert scraper._normalise_property_type("") == "unknown"

    def test_case_insensitive(self, scraper):
        assert scraper._normalise_property_type("DETACHED") == "detached"
        assert scraper._normalise_property_type("Semi-Detached House") == "semi-detached"


# ── _extract_postcode ──────────────────────────────────────────────────────

class TestExtractPostcode:
    def test_standard_postcode(self, scraper):
        assert scraper._extract_postcode("1 Test Road, Chatham ME4 6AA") == "ME46AA"

    def test_london_postcode(self, scraper):
        assert scraper._extract_postcode("Flat 2, London SE1 7PB") == "SE17PB"

    def test_no_postcode(self, scraper):
        assert scraper._extract_postcode("Somewhere in Kent") is None

    def test_postcode_with_extra_space(self, scraper):
        assert scraper._extract_postcode("Test Road ME4  6AA") == "ME46AA"


# ── _clean_address_text ───────────────────────────────────────────────────

class TestCleanAddressText:
    def test_removes_price(self, scraper):
        result = scraper._clean_address_text("£180,000 1 Test Road, Chatham")
        assert "£" not in result
        assert "Test Road" in result

    def test_removes_noise_phrases(self, scraper):
        result = scraper._clean_address_text("FEATURED PROPERTY 1 Test Road")
        assert "FEATURED" not in result
        assert "Test Road" in result

    def test_removes_trailing_property_type(self, scraper):
        result = scraper._clean_address_text("1 Test Road, ChathamFlat11")
        assert "Flat11" not in result

    def test_collapses_whitespace(self, scraper):
        result = scraper._clean_address_text("   1   Test   Road   ")
        assert result == "1 Test Road"

    def test_strips_punctuation(self, scraper):
        result = scraper._clean_address_text("- 1 Test Road, .")
        assert result == "1 Test Road"


# ── _parse_listing_date ───────────────────────────────────────────────────

class TestParseListingDate:
    def test_added_date(self, scraper):
        result = scraper._parse_listing_date("Added on 15/03/2026")
        assert result == "2026-03-15"

    def test_reduced_date(self, scraper):
        result = scraper._parse_listing_date("Reduced on 01/01/2026")
        assert result == "2026-01-01"

    def test_none_input(self, scraper):
        assert scraper._parse_listing_date(None) is None

    def test_no_date_in_string(self, scraper):
        assert scraper._parse_listing_date("Just listed") is None

    def test_invalid_date(self, scraper):
        assert scraper._parse_listing_date("Added on 32/13/2026") is None


# ── _extract_page_model ──────────────────────────────────────────────────

class TestExtractPageModel:
    def test_valid_page_model(self, scraper):
        prop_data = {"id": 12345, "address": {"displayAddress": "1 Test Road"}}
        html = f'<html>window.PAGE_MODEL = {{"propertyData": {json.dumps(prop_data)}}}</html>'
        result = scraper._extract_page_model(html)
        assert result["id"] == 12345
        assert result["address"]["displayAddress"] == "1 Test Road"

    def test_missing_page_model(self, scraper):
        html = "<html><body>No data here</body></html>"
        assert scraper._extract_page_model(html) is None

    def test_invalid_json(self, scraper):
        html = "window.PAGE_MODEL = {invalid json here}"
        assert scraper._extract_page_model(html) is None

    def test_nested_braces(self, scraper):
        prop_data = {"id": 1, "nested": {"deep": {"value": True}}}
        html = f'window.PAGE_MODEL = {{"propertyData": {json.dumps(prop_data)}}}'
        result = scraper._extract_page_model(html)
        assert result["nested"]["deep"]["value"] is True


# ── _extract_stations ─────────────────────────────────────────────────────

class TestExtractStations:
    def test_extracts_stations(self, scraper):
        prop_data = {
            "nearestStations": [
                {"name": "Chatham", "distance": 0.5},
                {"name": "Rochester", "distance": 1.2},
            ]
        }
        stations = scraper._extract_stations(prop_data)
        assert len(stations) == 2
        assert stations[0]["name"] == "Chatham"
        assert stations[0]["distance_m"] == round(0.5 * 1609.34)
        assert stations[0]["walk_min"] >= 1

    def test_empty_stations(self, scraper):
        assert scraper._extract_stations({}) == []
        assert scraper._extract_stations({"nearestStations": []}) == []

    def test_skips_invalid_entries(self, scraper):
        prop_data = {
            "nearestStations": [
                {"name": "Valid", "distance": 0.3},
                {"distance": 0.5},  # no name
                "invalid",
            ]
        }
        stations = scraper._extract_stations(prop_data)
        assert len(stations) == 1
        assert stations[0]["name"] == "Valid"


# ── _parse_listing_page (integration of detail parsing) ──────────────────

class TestParseListingPage:
    def _build_html(self, prop_data):
        """Build HTML with embedded PAGE_MODEL."""
        full_model = {"propertyData": prop_data}
        return f'<html>window.PAGE_MODEL = {json.dumps(full_model)}</html>'

    def test_parses_basic_listing(self, scraper):
        prop_data = {
            "id": 12345,
            "address": {"displayAddress": "1 Test Road, Chatham", "outcode": "ME4 ", "incode": "6AA"},
            "prices": {"primaryPrice": "£175,000"},
            "propertySubType": "Terraced",
            "bedrooms": 2,
            "bathrooms": 1,
            "location": {"latitude": 51.37, "longitude": 0.53},
            "text": {"description": "A lovely house"},
            "keyFeatures": {"features": ["Garden", "Parking"]},
        }
        html = self._build_html(prop_data)
        result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/12345")
        assert result is not None
        assert result.portal_id == "12345"
        assert result.price == 175000
        assert result.property_type == "terraced"
        assert result.bedrooms == 2
        assert result.postcode == "ME4 6AA"

    def test_parses_tenure_leasehold(self, scraper):
        prop_data = {
            "id": 99,
            "address": {"displayAddress": "Flat 1", "outcode": "ME1", "incode": "1AA"},
            "prices": {"primaryPrice": "£150,000"},
            "propertySubType": "Flat",
            "location": {},
            "tenure": {"tenureType": "Leasehold", "yearsRemainingOnLease": 95},
            "livingCosts": {"annualServiceCharge": 1200, "annualGroundRent": 150},
        }
        html = self._build_html(prop_data)
        result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/99")
        assert result.tenure == "leasehold"
        assert result.lease_years == 95
        assert result.service_charge_pa == 1200
        assert result.ground_rent_pa == 150

    def test_parses_tenure_freehold(self, scraper):
        prop_data = {
            "id": 100,
            "address": {"displayAddress": "1 Test Rd", "outcode": "ME4", "incode": "6AA"},
            "prices": {"primaryPrice": "£200,000"},
            "propertySubType": "Detached",
            "location": {},
            "tenure": {"tenureType": "Freehold"},
        }
        html = self._build_html(prop_data)
        result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/100")
        assert result.tenure == "freehold"
        assert result.lease_years is None

    def test_parses_share_of_freehold(self, scraper):
        prop_data = {
            "id": 101,
            "address": {"displayAddress": "Flat 2", "outcode": "ME1", "incode": "1BB"},
            "prices": {"primaryPrice": "£160,000"},
            "propertySubType": "Flat",
            "location": {},
            "tenure": {"tenureType": "Share of Freehold"},
        }
        html = self._build_html(prop_data)
        result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/101")
        assert result.tenure == "share_of_freehold"

    def test_extracts_floorplan_urls(self, scraper):
        prop_data = {
            "id": 200,
            "address": {"displayAddress": "Test", "outcode": "ME4", "incode": "6AA"},
            "prices": {"primaryPrice": "£175,000"},
            "propertySubType": "Flat",
            "location": {},
            "floorplanImages": [{"url": "https://example.com/fp1.jpg"}],
        }
        html = self._build_html(prop_data)
        result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/200")
        assert result.floorplan_urls == ["https://example.com/fp1.jpg"]

    def test_floorplan_fallback_keys(self, scraper):
        """Test that multiple Rightmove field names for floorplans are tried."""
        for key in ("floorplans", "floorPlanImages"):
            prop_data = {
                "id": 201,
                "address": {"displayAddress": "Test", "outcode": "ME4", "incode": "6AA"},
                "prices": {"primaryPrice": "£175,000"},
                "propertySubType": "Flat",
                "location": {},
                key: [{"srcUrl": "https://example.com/fp2.jpg"}],
            }
            html = self._build_html(prop_data)
            result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/201")
            assert result.floorplan_urls == ["https://example.com/fp2.jpg"], f"Failed with key={key}"

    def test_extracts_size_sqft(self, scraper):
        prop_data = {
            "id": 300,
            "address": {"displayAddress": "Test", "outcode": "ME4", "incode": "6AA"},
            "prices": {"primaryPrice": "£175,000"},
            "propertySubType": "Flat",
            "location": {},
            "sizings": [{"unit": "sqft", "minimumSize": 800}],
        }
        html = self._build_html(prop_data)
        result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/300")
        assert result.size_sqft == 800

    def test_converts_sqm_to_sqft(self, scraper):
        prop_data = {
            "id": 301,
            "address": {"displayAddress": "Test", "outcode": "ME4", "incode": "6AA"},
            "prices": {"primaryPrice": "£175,000"},
            "propertySubType": "Flat",
            "location": {},
            "sizings": [{"unit": "sqm", "minimumSize": 75}],
        }
        html = self._build_html(prop_data)
        result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/301")
        assert result.size_sqft == int(75 * 10.7639)

    def test_extracts_rooms(self, scraper):
        prop_data = {
            "id": 302,
            "address": {"displayAddress": "Test", "outcode": "ME4", "incode": "6AA"},
            "prices": {"primaryPrice": "£175,000"},
            "propertySubType": "Flat",
            "location": {},
            "rooms": [
                {"roomName": "Living Room", "width": 5.0, "length": 4.0, "unit": "m"},
                {"roomName": "Bedroom", "width": 3.5, "length": 3.0, "unit": "m"},
            ],
        }
        html = self._build_html(prop_data)
        result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/302")
        assert len(result.rooms) == 2
        assert result.rooms[0]["name"] == "Living Room"

    def test_returns_none_for_invalid_price(self, scraper):
        prop_data = {
            "id": 999,
            "address": {"displayAddress": "Test", "outcode": "ME4", "incode": "6AA"},
            "prices": {"primaryPrice": "POA"},
            "propertySubType": "Flat",
            "location": {},
        }
        html = self._build_html(prop_data)
        result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/999")
        assert result is None

    def test_returns_none_for_no_page_model(self, scraper):
        html = "<html><body>No data</body></html>"
        result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/1")
        assert result is None

    def test_extracts_council_tax_from_key_features(self, scraper):
        prop_data = {
            "id": 400,
            "address": {"displayAddress": "Test", "outcode": "ME4", "incode": "6AA"},
            "prices": {"primaryPrice": "£175,000"},
            "propertySubType": "Flat",
            "location": {},
            "keyFeatures": ["Council Tax Band B", "Garden"],
        }
        html = self._build_html(prop_data)
        result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/400")
        assert result.council_tax_band == "B"

    def test_extracts_epc_from_key_features(self, scraper):
        prop_data = {
            "id": 401,
            "address": {"displayAddress": "Test", "outcode": "ME4", "incode": "6AA"},
            "prices": {"primaryPrice": "£175,000"},
            "propertySubType": "Flat",
            "location": {},
            "keyFeatures": ["EPC Rating C", "Good condition"],
        }
        html = self._build_html(prop_data)
        result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/401")
        assert result.epc_rating == "C"

    def test_extracts_size_from_description_fallback(self, scraper):
        prop_data = {
            "id": 402,
            "address": {"displayAddress": "Test", "outcode": "ME4", "incode": "6AA"},
            "prices": {"primaryPrice": "£175,000"},
            "propertySubType": "Flat",
            "location": {},
            "text": {"description": "Beautiful flat with 750 sq ft of living space"},
        }
        html = self._build_html(prop_data)
        result = scraper._parse_listing_page(html, "https://www.rightmove.co.uk/properties/402")
        assert result.size_sqft == 750


# ── _parse_search_page_html ──────────────────────────────────────────────

class TestParseSearchPageHtml:
    def test_extracts_listings_from_cards(self, scraper):
        html = """
        <html><body>
        <div>
            <a href="/properties/12345">
                <div>£175,000 2 bed terraced house, 1 Test Road, Chatham ME4 6AA</div>
            </a>
        </div>
        </body></html>
        """
        listings = scraper._parse_search_page_html(html)
        assert len(listings) == 1
        assert listings[0].portal_id == "12345"
        assert listings[0].price == 175000

    def test_deduplicates_by_id(self, scraper):
        html = """
        <html><body>
        <div>
            <a href="/properties/12345">£175,000 1 Test Road, Chatham ME4 6AA</a>
            <a href="/properties/12345">View details</a>
        </div>
        </body></html>
        """
        listings = scraper._parse_search_page_html(html)
        assert len(listings) == 1

    def test_no_property_links(self, scraper):
        html = "<html><body><div>No properties found</div></body></html>"
        listings = scraper._parse_search_page_html(html)
        assert listings == []


# ── HttpClient ────────────────────────────────────────────────────────────

class TestHttpClient:
    def test_bot_block_markers(self):
        """Verify bot block detection markers are set."""
        client = HttpClient.__new__(HttpClient)
        assert "captcha" in client.BOT_BLOCK_MARKERS
        assert "robot" in client.BOT_BLOCK_MARKERS

    def test_load_user_agents_fallback(self, tmp_path, monkeypatch):
        """When no UA pool file exists, falls back to default UA."""
        monkeypatch.chdir(tmp_path)
        client = HttpClient(config={})
        assert len(client.ua_pool) >= 1
        assert "Mozilla" in client.ua_pool[0]

    def test_get_headers_includes_user_agent(self):
        client = HttpClient(config={})
        headers = client._get_headers()
        assert "User-Agent" in headers
        assert "Mozilla" in headers["User-Agent"]
