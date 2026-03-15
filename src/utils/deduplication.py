"""URL normalisation and property deduplication."""

import re
from urllib.parse import urlparse, urlencode, parse_qs


# Tracking parameters to strip from URLs
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "fbclid", "gclid", "msclkid", "ref", "clickid", "channel",
}

# Address normalisation replacements
ADDRESS_REPLACEMENTS = {
    " road": " rd",
    " street": " st",
    " avenue": " ave",
    " lane": " ln",
    " drive": " dr",
    " close": " cl",
    " crescent": " cres",
    " terrace": " ter",
    " gardens": " gdns",
    " grove": " gr",
    " place": " pl",
    " court": " ct",
    " square": " sq",
    " mews": " mews",
    " rise": " rise",
    " way": " way",
}


def normalise_url(url: str) -> str:
    """Normalise a property listing URL by removing tracking parameters."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    # Remove tracking parameters
    clean_params = {
        k: v for k, v in params.items() if k.lower() not in TRACKING_PARAMS
    }

    # Rebuild URL
    clean_query = urlencode(clean_params, doseq=True)
    normalised = parsed._replace(
        query=clean_query,
        fragment="",
    ).geturl()

    # Remove trailing slashes
    return normalised.rstrip("/")


def normalise_address(address: str) -> str:
    """Normalise an address for cross-portal matching."""
    addr = address.lower().strip()

    # Remove common prefixes
    for prefix in ("flat ", "apartment ", "apt ", "the "):
        if addr.startswith(prefix):
            addr = addr[len(prefix):]

    # Standardise road types
    for full, short in ADDRESS_REPLACEMENTS.items():
        addr = addr.replace(full, short)

    # Remove all punctuation except hyphens
    addr = re.sub(r"[^\w\s-]", "", addr)

    # Collapse whitespace
    addr = re.sub(r"\s+", " ", addr).strip()

    return addr


def extract_postcode(text: str) -> str | None:
    """Extract a UK postcode from text."""
    match = re.search(
        r"([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})", text.upper()
    )
    return match.group(1).replace(" ", "").upper() if match else None


def is_cross_portal_match(
    addr1: str, postcode1: str, price1: int,
    addr2: str, postcode2: str, price2: int,
    price_tolerance: int = 1000,
) -> bool:
    """Check if two listings from different portals are the same property."""
    if not postcode1 or not postcode2:
        return False

    # Postcodes must match (normalised: no spaces, uppercase)
    pc1 = postcode1.replace(" ", "").upper()
    pc2 = postcode2.replace(" ", "").upper()
    if pc1 != pc2:
        return False

    # Price must be within tolerance
    if abs(price1 - price2) > price_tolerance:
        return False

    # Normalised addresses should be similar
    norm1 = normalise_address(addr1)
    norm2 = normalise_address(addr2)

    # Exact match after normalisation
    if norm1 == norm2:
        return True

    # Check if one contains the other (handles different detail levels)
    if norm1 in norm2 or norm2 in norm1:
        return True

    return False
