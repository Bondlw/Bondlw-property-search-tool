"""Extract property size from floor plan images using Claude vision."""

import base64
import json
import logging
import re
import time

import requests

logger = logging.getLogger(__name__)

PROMPT = """This is a floor plan image for a UK residential property.

Your task: extract the TOTAL floor area in square feet.

Instructions:
- Look for an overall/gross internal area figure (often labelled "Total", "GIA", "Gross Internal Area", or similar)
- If the total is given in square metres (sq m / m²), convert to sq ft by multiplying by 10.764
- If there is no explicit total, add up the individual room areas shown on the plan
- Return ONLY a JSON object with a single key "size_sqft" containing an integer, e.g. {"size_sqft": 650}
- If you cannot determine the floor area from this image, return {"size_sqft": null}
- Do not include any other text, explanation or markdown
"""


class FloorplanVisionExtractor:
    def __init__(self, api_key: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._http = requests.Session()
        self._http.headers["User-Agent"] = "PropertySearchTool/1.0 (personal use)"

    def _fetch_image_b64(self, url: str) -> tuple[str, str] | None:
        """Download image and return (base64_data, media_type) or None."""
        try:
            r = self._http.get(url, timeout=15)
            if r.status_code != 200:
                return None
            ct = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            if ct not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                ct = "image/jpeg"
            return base64.standard_b64encode(r.content).decode(), ct
        except Exception as e:
            logger.debug(f"Failed to fetch floor plan image {url}: {e}")
            return None

    def extract_size(self, floorplan_url: str) -> int | None:
        """Return size in sqft extracted from a floor plan image URL, or None."""
        img = self._fetch_image_b64(floorplan_url)
        if not img:
            return None

        b64_data, media_type = img
        try:
            resp = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=64,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_data}},
                        {"type": "text", "text": PROMPT},
                    ],
                }],
            )
            raw = resp.content[0].text.strip()
            # Strip markdown code fences if present
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
            data = json.loads(raw)
            val = data.get("size_sqft")
            if val is not None:
                val = int(val)
                if 100 <= val <= 15000:   # sanity range for residential
                    return val
        except Exception as e:
            logger.debug(f"Vision extraction failed for {floorplan_url}: {e}")
        return None


def run_floorplan_size_extraction(db_path: str, api_key: str, limit: int = 0, delay: float = 0.5) -> int:
    """
    Extract size_sqft from floor plan images for properties that have floor plans
    but no size data. Updates the DB directly.

    Returns the count of properties updated.
    """
    import sqlite3

    extractor = FloorplanVisionExtractor(api_key)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id, address, floorplan_urls
        FROM properties
        WHERE size_sqft IS NULL
          AND floorplan_urls IS NOT NULL
          AND floorplan_urls != '[]'
          AND floorplan_urls != ''
          AND is_active = 1
        ORDER BY id DESC
    """)
    rows = cur.fetchall()

    if limit:
        rows = rows[:limit]

    updated = 0
    for i, row in enumerate(rows):
        prop_id = row["id"]
        address = row["address"] or f"ID {prop_id}"

        try:
            urls = json.loads(row["floorplan_urls"])
        except (json.JSONDecodeError, TypeError):
            continue

        if not urls:
            continue

        logger.info(f"[{i+1}/{len(rows)}] {address}")
        size = extractor.extract_size(urls[0])
        if size:
            cur.execute("UPDATE properties SET size_sqft = ? WHERE id = ?", (size, prop_id))
            conn.commit()
            updated += 1
            logger.info(f"  → {size} sqft")
        else:
            logger.debug(f"  → no size extracted")

        if delay:
            time.sleep(delay)

    conn.close()
    return updated
