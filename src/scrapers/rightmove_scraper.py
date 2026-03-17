"""Rightmove property scraper.

Scrapes search results and individual listing pages from Rightmove.
Search pages: HTML parsing of property cards.
Listing pages: __NEXT_DATA__ JSON or HTML fallback.
"""

import json
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from ..storage.models import RawListing
from .base_scraper import BaseScraper
from .http_client import HttpClient

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.rightmove.co.uk/property-for-sale/find.html"
PROPERTY_URL_BASE = "https://www.rightmove.co.uk/properties/"


class RightmoveScraper(BaseScraper):
    """Scraper for Rightmove property listings."""

    def __init__(self, http_client: HttpClient):
        self.client = http_client

    def get_portal_name(self) -> str:
        return "rightmove"

    def search(self, area_config: dict, budget_config: dict) -> list[RawListing]:
        """Search Rightmove for properties in the given area."""
        location_id = area_config.get("rightmove_id", "")
        if not location_id:
            logger.warning(
                f"No Rightmove location ID for {area_config['name']}, skipping"
            )
            return []

        # Determine price range — use the widest range across tenure types
        # No stretch buffer — absolute_max IS the max listed price we'd consider
        max_price = max(
            budget_config.get("freehold", {}).get("absolute_max", 200000),
            budget_config.get("leasehold", {}).get("absolute_max", 200000),
        )

        all_listings = []
        index = 0
        max_pages = 42

        for page in range(max_pages):
            params = {
                "searchType": "SALE",
                "locationIdentifier": location_id,
                "maxPrice": max_price,
                "propertyTypes": "detached,semi-detached,terraced,flat",
                "dontShow": "retirement,sharedOwnership,auction",
                "sortType": "6",
                "index": index,
            }

            url = SEARCH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
            logger.info(
                f"Searching {area_config['name']} page {page + 1}: {url}"
            )

            html = self.client.get_text(url)
            if not html:
                logger.error(f"Failed to fetch search page for {area_config['name']}")
                break

            listings = self._parse_search_page_html(html)
            if not listings:
                logger.info(
                    f"No more results for {area_config['name']} after page {page + 1}"
                )
                break

            all_listings.extend(listings)

            # Check for next page — look for pagination
            soup = BeautifulSoup(html, "html.parser")
            # If we found fewer than ~20 listings, likely last page
            if len(listings) < 20:
                break
            index += 24

        logger.info(
            f"Found {len(all_listings)} listings in {area_config['name']}"
        )
        return all_listings

    def get_listing_detail(self, url: str) -> RawListing | None:
        """Fetch full details for a single Rightmove listing."""
        html = self.client.get_text(url)
        if not html:
            return None

        return self._parse_listing_page(html, url)

    def _parse_search_page_html(self, html: str) -> list[RawListing]:
        """Parse property cards from Rightmove search results HTML."""
        soup = BeautifulSoup(html, "html.parser")
        listings = []

        # Find all property links: /properties/{ID}
        property_links = soup.find_all("a", href=re.compile(r"/properties/\d+"))

        # Deduplicate by property ID (multiple links per card)
        seen_ids = set()
        for link in property_links:
            href = link.get("href", "")
            id_match = re.search(r"/properties/(\d+)", href)
            if not id_match:
                continue

            prop_id = id_match.group(1)
            if prop_id in seen_ids:
                continue
            seen_ids.add(prop_id)

            # Walk up to find the property card container
            card = self._find_property_card(link)
            if not card:
                continue

            listing = self._extract_from_card(card, prop_id)
            if listing:
                listings.append(listing)

        return listings

    def _find_property_card(self, link_element) -> Optional[BeautifulSoup]:
        """Walk up from a property link to find the card container."""
        # Walk up to find a container div that holds the full card
        element = link_element
        for _ in range(10):
            parent = element.parent
            if parent is None:
                break
            # Look for a card-level container (usually has price + address)
            text = parent.get_text()
            if "£" in text and len(text) > 50:
                return parent
            element = parent
        return link_element.parent

    def _extract_from_card(self, card, prop_id: str) -> RawListing | None:
        """Extract property data from an HTML card element."""
        try:
            card_text = card.get_text(separator=" ", strip=True)

            # Extract price
            price_match = re.search(r"£([\d,]+)", card_text)
            if not price_match:
                return None
            price = int(price_match.group(1).replace(",", ""))

            # Extract address — find the main link text that contains an address
            address = ""
            address_links = card.find_all(
                "a", href=re.compile(rf"/properties/{prop_id}")
            )
            for a in address_links:
                text = a.get_text(strip=True)
                text = self._clean_address_text(text)
                # Address typically has a comma (street, area, postcode)
                if "," in text and len(text) > 10:
                    address = text
                    break
            if not address:
                for a in address_links:
                    text = a.get_text(strip=True)
                    text = self._clean_address_text(text)
                    if text and len(text) > 5:
                        address = text
                        break

            postcode = self._extract_postcode(address) if address else None

            # Extract property type and bedrooms
            prop_type = "unknown"
            bedrooms = None
            bathrooms = None

            # Look for property type keywords in card text
            type_keywords = [
                "detached", "semi-detached", "terraced", "flat",
                "apartment", "maisonette", "bungalow", "cottage",
                "end of terrace",
            ]
            card_lower = card_text.lower()
            for kw in type_keywords:
                if kw in card_lower:
                    prop_type = kw
                    break

            # Look for bedroom count — pattern like "2 bed" or "3 bedroom"
            bed_match = re.search(r"(\d+)\s*bed", card_lower)
            if bed_match:
                bedrooms = int(bed_match.group(1))

            # Look for bathroom count
            bath_match = re.search(r"(\d+)\s*bath", card_lower)
            if bath_match:
                bathrooms = int(bath_match.group(1))

            # Extract agent name — often in smaller text at bottom
            agent_name = None
            agent_spans = card.find_all(
                string=re.compile(r"(estate|property|homes|lettings|sales)", re.I)
            )
            for span in agent_spans:
                text = span.strip()
                if len(text) > 3 and len(text) < 60:
                    agent_name = text
                    break

            listing = RawListing(
                portal="rightmove",
                portal_id=prop_id,
                url=f"{PROPERTY_URL_BASE}{prop_id}",
                title=address or f"Property {prop_id}",
                price=price,
                address=address,
                postcode=postcode or "",
                property_type=self._normalise_property_type(prop_type),
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                agent_name=agent_name,
            )

            return listing

        except Exception as e:
            logger.warning(f"Failed to extract from card {prop_id}: {e}")
            return None

    def _parse_listing_page(self, html: str, url: str) -> RawListing | None:
        """Parse a full listing detail page."""
        prop_data = self._extract_page_model(html)

        if not prop_data:
            logger.warning(f"No property data found on listing page: {url}")
            return None

        try:
            prop_id = str(prop_data.get("id", ""))
            address_data = prop_data.get("address", {})
            address = address_data.get("displayAddress", "")
            postcode = address_data.get("outcode", "")
            if address_data.get("incode"):
                postcode = f"{postcode}{address_data['incode']}"

            price_data = prop_data.get("prices", {})
            price = price_data.get("primaryPrice", "").replace("£", "").replace(",", "")
            try:
                price = int(price)
            except (ValueError, TypeError):
                return None

            location = prop_data.get("location", {})
            prop_type = (prop_data.get("propertySubType") or "").lower()

            # Key features
            key_features = []
            kf_data = prop_data.get("keyFeatures", {})
            if isinstance(kf_data, dict):
                key_features = kf_data.get("features", [])
            elif isinstance(kf_data, list):
                key_features = kf_data

            # Description
            description = ""
            text_data = prop_data.get("text", {})
            if isinstance(text_data, dict):
                description = text_data.get("description", "")
            elif isinstance(text_data, str):
                description = text_data

            # Tenure and leasehold details
            tenure_info = prop_data.get("tenure", {})
            tenure = None
            lease_years = None
            if isinstance(tenure_info, dict):
                tenure_type = (tenure_info.get("tenureType") or "").lower()
                if "freehold" in tenure_type:
                    tenure = "freehold"
                elif "leasehold" in tenure_type:
                    tenure = "leasehold"
                elif "share" in tenure_type:
                    tenure = "share_of_freehold"
                lease_years = (
                    tenure_info.get("yearsRemainingOnLease")
                    or tenure_info.get("yearsRemaining")
                )
            elif isinstance(tenure_info, str):
                tenure = self._parse_tenure_string(tenure_info)

            # Service charge and ground rent
            # livingCosts holds the structured financial fields
            living_costs = prop_data.get("livingCosts") or {}

            service_charge_pa = (
                int(living_costs["annualServiceCharge"])
                if living_costs.get("annualServiceCharge") is not None
                else self._extract_annual_charge(prop_data, "serviceCharge")
            )
            ground_rent_pa = (
                int(living_costs["annualGroundRent"])
                if living_costs.get("annualGroundRent") is not None
                else self._extract_annual_charge(prop_data, "groundRent")
            )

            # Council tax — structured field first, then keyFeatures text
            council_tax = (
                living_costs.get("councilTaxBand")
                or prop_data.get("councilTaxBand")
            )
            if not council_tax:
                for feat in (key_features if isinstance(key_features, list) else []):
                    m = re.search(r"council tax band\s*([A-H])", str(feat), re.IGNORECASE)
                    if m:
                        council_tax = m.group(1).upper()
                        break

            # EPC — keyFeatures text (PAGE_MODEL only exposes certificate URL, not rating)
            epc_rating = None
            for feat in (key_features if isinstance(key_features, list) else []):
                m = re.search(r"epc\s+(?:rating|band)[:\s]+([A-G])", str(feat), re.IGNORECASE)
                if not m:
                    m = re.search(r"energy\s+(?:rating|band)[:\s]+([A-G])", str(feat), re.IGNORECASE)
                if m:
                    epc_rating = m.group(1).upper()
                    break

            # Images
            images = []
            for img in prop_data.get("images", []):
                if isinstance(img, dict):
                    img_url = img.get("url") or img.get("srcUrl")
                    if img_url:
                        images.append(img_url)

            # Floor plans
            floorplan_urls = []
            for fp in (prop_data.get("floorplanImages") or []):
                if isinstance(fp, dict):
                    fp_url = fp.get("url") or fp.get("srcUrl")
                    if fp_url:
                        floorplan_urls.append(fp_url)

            # Brochure and video URLs
            property_urls = prop_data.get("propertyUrls") or {}
            video_url = property_urls.get("virtualTourUrl") or None
            brochure_url = property_urls.get("brochureUrl") or None

            # Room dimensions
            rooms = []
            for r in (prop_data.get("rooms") or []):
                if isinstance(r, dict):
                    room_name = r.get("roomName") or r.get("name") or ""
                    width = r.get("width")
                    length = r.get("length")
                    unit = r.get("unit", "m")
                    if room_name and (width is not None or length is not None):
                        rooms.append({
                            "name": room_name,
                            "width": width,
                            "length": length,
                            "unit": unit,
                        })

            listing = RawListing(
                portal="rightmove",
                portal_id=prop_id,
                url=url,
                title=address,
                price=price,
                address=address,
                postcode=postcode,
                property_type=self._normalise_property_type(prop_type),
                bedrooms=prop_data.get("bedrooms"),
                bathrooms=prop_data.get("bathrooms"),
                tenure=tenure,
                lease_years=lease_years,
                service_charge_pa=service_charge_pa,
                ground_rent_pa=ground_rent_pa,
                council_tax_band=council_tax,
                epc_rating=epc_rating,
                description=description,
                key_features=key_features if isinstance(key_features, list) else [],
                images=images,
                floorplan_urls=floorplan_urls,
                video_url=video_url,
                brochure_url=brochure_url,
                rooms=rooms,
                agent_name=(
                    prop_data.get("customer", {}).get("branchDisplayName")
                    or prop_data.get("customer", {}).get("brandTradingName")
                ),
                first_listed_date=self._parse_listing_date(
                    prop_data.get("listingHistory", {}).get("listingUpdateReason")
                ),
                latitude=location.get("latitude"),
                longitude=location.get("longitude"),
            )

            listing.nearest_stations = self._extract_stations(prop_data)
            return listing

        except Exception as e:
            logger.warning(f"Failed to parse listing detail: {e}")
            return None

    def _extract_stations(self, prop_data: dict) -> list[dict]:
        """Extract nearest train stations from PAGE_MODEL data."""
        stations = []
        for s in prop_data.get("nearestStations", []):
            if isinstance(s, dict) and s.get("name"):
                dist_miles = s.get("distance", 0)
                dist_m = dist_miles * 1609.34
                walk_min = max(1, round(dist_m / 1.4 / 60))  # 1.4 m/s walking speed
                stations.append({
                    "name": s["name"],
                    "distance_m": round(dist_m),
                    "walk_min": walk_min,
                })
        return stations

    def _clean_address_text(self, text: str) -> str:
        """Remove price, status labels and other noise from address text."""
        # Remove price patterns like "£180,000"
        text = re.sub(r"£[\d,]+", "", text)
        # Remove common noise phrases
        noise = [
            "FEATURED PROPERTY", "PREMIUM LISTING",
            "Guide Price", "Premium Listing", "Offers Over",
            "Offers in Excess of", "Offers in Region of",
            "Price on Application", "POA", "From", "Shared Ownership",
            "New Build", "Featured Property", "Online Viewing",
        ]
        for phrase in noise:
            text = text.replace(phrase, "")
        # Remove trailing property type + bed/bath counts (e.g. "Flat11", "Apartment21", "Semi-detached house32")
        text = re.sub(
            r"(?:Apartment|Flat|Maisonette|Terraced house|Semi-detached house|"
            r"Detached house|Bungalow|Cottage|End of terrace house|House|Property)\d*$",
            "", text
        )
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Remove leading/trailing punctuation
        text = text.strip(" -,.")
        return text

    def _parse_listing_date(self, reason_str: str | None) -> str | None:
        """Parse a date from 'Added on DD/MM/YYYY' or 'Reduced on DD/MM/YYYY'."""
        if not reason_str:
            return None
        match = re.search(r"(\d{2}/\d{2}/\d{4})", reason_str)
        if match:
            from datetime import datetime
            try:
                dt = datetime.strptime(match.group(1), "%d/%m/%Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                return None
        return None

    def _extract_page_model(self, html: str) -> dict | None:
        """Extract propertyData from window.PAGE_MODEL JSON in the HTML."""
        marker = "window.PAGE_MODEL = "
        idx = html.find(marker)
        if idx == -1:
            return None

        json_start = idx + len(marker)
        depth = 0
        i = json_start
        while i < len(html):
            ch = html[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        else:
            return None

        try:
            data = json.loads(html[json_start : i + 1])
            return data.get("propertyData", {})
        except json.JSONDecodeError:
            return None

    def _extract_postcode(self, address: str) -> str | None:
        """Extract postcode from an address string."""
        match = re.search(
            r"([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})", address.upper()
        )
        return match.group(1).replace(" ", "") if match else None

    def _normalise_property_type(self, prop_type: str) -> str:
        """Normalise property type string."""
        prop_type = prop_type.lower().strip()
        if any(t in prop_type for t in ("flat", "apartment", "maisonette")):
            return "flat"
        if "terraced" in prop_type:
            return "terraced"
        if "semi" in prop_type:
            return "semi-detached"
        if "detached" in prop_type:
            return "detached"
        if "bungalow" in prop_type:
            return "bungalow"
        if "cottage" in prop_type:
            return "cottage"
        if "end of terrace" in prop_type:
            return "terraced"
        return prop_type or "unknown"

    def _extract_tenure_from_tags(self, prop_data: dict) -> str | None:
        """Try to extract tenure from property tags/badges in search results."""
        tags = prop_data.get("displayStatus", "").lower()
        if "freehold" in tags:
            return "freehold"
        if "leasehold" in tags:
            return "leasehold"
        return None

    def _parse_tenure_string(self, tenure_str: str) -> str | None:
        """Parse a tenure string into a normalised value."""
        tenure_lower = tenure_str.lower()
        if "freehold" in tenure_lower and "leasehold" not in tenure_lower:
            return "freehold"
        if "leasehold" in tenure_lower:
            return "leasehold"
        if "share of freehold" in tenure_lower:
            return "share_of_freehold"
        return None

    def _extract_annual_charge(
        self, prop_data: dict, field_name: str
    ) -> int | None:
        """Extract an annual charge (service charge or ground rent) from listing data."""
        charge_data = prop_data.get(field_name)

        if charge_data is None:
            return None

        if isinstance(charge_data, (int, float)):
            return int(charge_data)

        if isinstance(charge_data, dict):
            amount = charge_data.get("amount")
            if amount is None:
                return None
            try:
                amount = int(float(str(amount).replace("£", "").replace(",", "")))
            except (ValueError, TypeError):
                return None

            period = charge_data.get("period", "").lower()
            if "month" in period:
                return amount * 12
            if "quarter" in period:
                return amount * 4
            if "week" in period:
                return amount * 52
            return amount  # Assume annual

        if isinstance(charge_data, str):
            # Try to parse a string like "£1,200 per year"
            match = re.search(r"£?([\d,]+)", charge_data)
            if match:
                try:
                    amount = int(match.group(1).replace(",", ""))
                except ValueError:
                    return None
                charge_lower = charge_data.lower()
                if "month" in charge_lower:
                    return amount * 12
                if "quarter" in charge_lower:
                    return amount * 4
                return amount

        return None
