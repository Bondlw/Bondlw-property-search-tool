"""CRUD operations for the property search database."""

import json
from datetime import date, datetime
from typing import Optional

from .database import Database
from .models import Property, RawListing


class PropertyRepository:
    """Database operations for properties."""

    def __init__(self, db: Database):
        self.db = db

    def property_exists(self, portal: str, portal_id: str) -> Optional[int]:
        """Check if a property exists. Returns property ID or None."""
        row = self.db.conn.execute(
            "SELECT id FROM properties WHERE portal = ? AND portal_id = ?",
            (portal, portal_id),
        ).fetchone()
        return row["id"] if row else None

    def find_by_normalised_url(self, url_normalised: str) -> Optional[int]:
        """Find property by normalised URL. Returns property ID or None."""
        row = self.db.conn.execute(
            "SELECT id FROM properties WHERE url_normalised = ?",
            (url_normalised,),
        ).fetchone()
        return row["id"] if row else None

    def insert_property(self, listing: RawListing, url_normalised: str) -> int:
        """Insert a new property. Returns the new property ID."""
        today = date.today().isoformat()
        cursor = self.db.conn.execute(
            """INSERT INTO properties (
                portal, portal_id, url, url_normalised, title, price,
                address, postcode, property_type, bedrooms, bathrooms,
                tenure, lease_years, service_charge_pa, ground_rent_pa,
                council_tax_band, epc_rating, description, key_features,
                agent_name, latitude, longitude, images,
                first_seen_date, last_seen_date, first_listed_date,
                is_active, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'active')""",
            (
                listing.portal,
                listing.portal_id,
                listing.url,
                url_normalised,
                listing.title,
                listing.price,
                listing.address,
                listing.postcode,
                listing.property_type,
                listing.bedrooms,
                listing.bathrooms,
                listing.tenure,
                listing.lease_years,
                listing.service_charge_pa,
                listing.ground_rent_pa,
                listing.council_tax_band,
                listing.epc_rating,
                listing.description,
                json.dumps(listing.key_features),
                listing.agent_name,
                listing.latitude,
                listing.longitude,
                json.dumps(listing.images) if listing.images else None,
                today,
                today,
                listing.first_listed_date,
            ),
        )
        prop_id = cursor.lastrowid

        # Record initial price in history — use portal listing date if available
        self.db.conn.execute(
            """INSERT INTO price_history (property_id, price, recorded_date)
               VALUES (?, ?, ?)""",
            (prop_id, listing.price, listing.first_listed_date or today),
        )
        self.db.conn.commit()
        return prop_id

    def update_property(self, prop_id: int, listing: RawListing) -> bool:
        """Update existing property from search results.

        Only updates price, last_seen_date, and is_active.
        Does NOT overwrite detail fields (tenure, description, etc.)
        that may have been populated by a detail fetch.
        Returns True if price changed.
        """
        today = date.today().isoformat()
        old = self.db.conn.execute(
            "SELECT price FROM properties WHERE id = ?", (prop_id,)
        ).fetchone()

        price_changed = old is not None and old["price"] != listing.price

        price_reduced = 0
        if price_changed and old is not None:
            price_reduced = 1 if listing.price < old["price"] else 0

        self.db.conn.execute(
            """UPDATE properties SET
                price = ?,
                last_seen_date = ?,
                is_active = 1,
                status = 'active',
                price_reduced = ?,
                updated_at = datetime('now')
            WHERE id = ?""",
            (listing.price, today, price_reduced, prop_id),
        )

        if price_changed and old is not None:
            change = listing.price - old["price"]
            change_pct = (change / old["price"]) * 100 if old["price"] > 0 else 0
            self.db.conn.execute(
                """INSERT INTO price_history
                   (property_id, price, recorded_date, change_amount, change_pct)
                   VALUES (?, ?, ?, ?, ?)""",
                (prop_id, listing.price, today, change, round(change_pct, 2)),
            )

        self.db.conn.commit()
        return price_changed

    def update_property_details(self, prop_id: int, listing: RawListing) -> None:
        """Update a property with detail-level fields only.

        Only overwrites fields that are non-null in the listing,
        preserving existing data from search results.
        """
        updates = []
        values = []

        detail_fields = {
            "address": listing.address,
            "postcode": listing.postcode,
            "property_type": listing.property_type,
            "bedrooms": listing.bedrooms,
            "bathrooms": listing.bathrooms,
            "tenure": listing.tenure,
            "lease_years": listing.lease_years,
            "service_charge_pa": listing.service_charge_pa,
            "ground_rent_pa": listing.ground_rent_pa,
            "council_tax_band": listing.council_tax_band,
            "epc_rating": listing.epc_rating,
            "description": listing.description,
            "key_features": json.dumps(listing.key_features) if listing.key_features else None,
            "agent_name": listing.agent_name,
            "latitude": listing.latitude,
            "longitude": listing.longitude,
            "first_listed_date": listing.first_listed_date,
            "images": json.dumps(listing.images) if listing.images else None,
            "floorplan_urls": json.dumps(listing.floorplan_urls) if listing.floorplan_urls else None,
            "video_url": listing.video_url,
            "brochure_url": listing.brochure_url,
            "rooms": json.dumps(listing.rooms) if listing.rooms else None,
            "size_sqft": listing.size_sqft,
        }

        for col, val in detail_fields.items():
            if val is not None and val != "" and val != []:
                updates.append(f"{col} = ?")
                values.append(val)

        if not updates:
            return

        updates.append("updated_at = datetime('now')")
        values.append(prop_id)

        sql = f"UPDATE properties SET {', '.join(updates)} WHERE id = ?"
        self.db.conn.execute(sql, values)
        self.db.conn.commit()

    def get_properties_needing_details(self) -> list[dict]:
        """Get active properties that haven't been detail-scraped yet, or are missing key data."""
        rows = self.db.conn.execute(
            """SELECT id, url, portal_id FROM properties
               WHERE is_active = 1
               AND (
                   description IS NULL OR description = ''
                   OR images IS NULL OR images = '' OR images = '[]'
                   OR service_charge_pa IS NULL
                   OR ground_rent_pa IS NULL
               )
               ORDER BY first_seen_date DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_property(self, prop_id: int) -> Optional[dict]:
        """Get a property by ID as a dict."""
        row = self.db.conn.execute(
            "SELECT * FROM properties WHERE id = ?", (prop_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_active_properties(self) -> list[dict]:
        """Get all active properties."""
        rows = self.db.conn.execute(
            "SELECT * FROM properties WHERE is_active = 1 ORDER BY first_seen_date DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_new_properties(self, since_date: str) -> list[dict]:
        """Get properties first seen on or after the given date."""
        rows = self.db.conn.execute(
            "SELECT * FROM properties WHERE first_seen_date >= ? AND is_active = 1",
            (since_date,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_price_history(self, prop_id: int) -> list[dict]:
        """Get price history for a property, including cross-listing history.

        Finds other listings of the same physical property (re-listings with
        new portal IDs) by matching on street name + lat/lng proximity, then
        merges their price records into a single timeline.
        """
        # Get this property's details for cross-referencing
        prop = self.db.conn.execute(
            "SELECT address, latitude, longitude FROM properties WHERE id = ?",
            (prop_id,),
        ).fetchone()

        if not prop or not prop["address"]:
            rows = self.db.conn.execute(
                "SELECT * FROM price_history WHERE property_id = ? ORDER BY recorded_date",
                (prop_id,),
            ).fetchall()
            return [dict(r) for r in rows]

        address = prop["address"].strip()
        street = address.split(",")[0].strip()
        if len(street) < 5:
            rows = self.db.conn.execute(
                "SELECT * FROM price_history WHERE property_id = ? ORDER BY recorded_date",
                (prop_id,),
            ).fetchall()
            return [dict(r) for r in rows]

        # Find candidates with the same street name
        candidates = self.db.conn.execute(
            """SELECT id, latitude, longitude FROM properties
               WHERE LOWER(TRIM(SUBSTR(address, 1, INSTR(address || ',', ',') - 1))) = ?""",
            (street.lower(),),
        ).fetchall()

        # Filter to same physical location using lat/lng proximity (~50m radius)
        lat = prop["latitude"]
        lng = prop["longitude"]
        related_ids = [prop_id]

        if lat and lng:
            for c in candidates:
                if c["id"] == prop_id:
                    continue
                c_lat, c_lng = c["latitude"], c["longitude"]
                if c_lat and c_lng:
                    # ~50m threshold: 0.0005 degrees ≈ 55m at UK latitudes
                    if abs(c_lat - lat) < 0.0005 and abs(c_lng - lng) < 0.0005:
                        related_ids.append(c["id"])
        else:
            # No coordinates — fall back to just street match (less reliable)
            related_ids = [c["id"] for c in candidates]

        if len(related_ids) <= 1:
            rows = self.db.conn.execute(
                "SELECT * FROM price_history WHERE property_id = ? ORDER BY recorded_date",
                (prop_id,),
            ).fetchall()
            return [dict(r) for r in rows]

        # Merge price histories from all related listings
        placeholders = ",".join("?" for _ in related_ids)
        rows = self.db.conn.execute(
            f"""SELECT ph.*, p.first_listed_date
                FROM price_history ph
                JOIN properties p ON p.id = ph.property_id
                WHERE ph.property_id IN ({placeholders})
                ORDER BY COALESCE(p.first_listed_date, ph.recorded_date), ph.recorded_date, ph.price""",
            related_ids,
        ).fetchall()

        # Deduplicate — skip consecutive entries at the same price (re-listings)
        merged = []
        last_price = None
        for r in rows:
            if r["price"] == last_price:
                continue
            merged.append(dict(r))
            last_price = r["price"]

        # Recalculate change_amount and change_pct for the merged timeline
        for i, entry in enumerate(merged):
            if i == 0:
                entry["change_amount"] = None
                entry["change_pct"] = None
            else:
                prev_price = merged[i - 1]["price"]
                entry["change_amount"] = entry["price"] - prev_price
                entry["change_pct"] = round(
                    (entry["change_amount"] / prev_price) * 100, 2
                ) if prev_price else None

        return merged

    def get_reduced_properties(self) -> list[dict]:
        """Get properties that have had price reductions."""
        rows = self.db.conn.execute(
            """SELECT DISTINCT p.* FROM properties p
               INNER JOIN price_history ph ON p.id = ph.property_id
               WHERE ph.change_amount < 0 AND p.is_active = 1
               ORDER BY ph.recorded_date DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stale_properties(self, min_days: int = 30) -> list[dict]:
        """Get properties on the market for at least min_days."""
        rows = self.db.conn.execute(
            """SELECT * FROM properties
               WHERE is_active = 1
               AND julianday('now') - julianday(first_seen_date) >= ?
               ORDER BY first_seen_date ASC""",
            (min_days,),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_inactive(self, prop_id: int, status: str = "removed"):
        """Mark a property as inactive."""
        self.db.conn.execute(
            "UPDATE properties SET is_active = 0, status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, prop_id),
        )
        self.db.conn.commit()

    def add_exclusion(self, prop_id: int, reason: str, excluded_by: str = "user"):
        """Exclude a property."""
        self.db.conn.execute(
            """INSERT OR REPLACE INTO exclusions (property_id, reason, excluded_by)
               VALUES (?, ?, ?)""",
            (prop_id, reason, excluded_by),
        )
        self.db.conn.commit()

    def remove_exclusion(self, prop_id: int):
        """Remove an exclusion."""
        self.db.conn.execute(
            "DELETE FROM exclusions WHERE property_id = ?", (prop_id,)
        )
        self.db.conn.commit()

    def get_exclusions(self) -> list[dict]:
        """Get all excluded properties."""
        rows = self.db.conn.execute(
            """SELECT e.*, p.address, p.price, p.url
               FROM exclusions e
               INNER JOIN properties p ON e.property_id = p.id
               ORDER BY e.excluded_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Get database statistics."""
        total = self.db.conn.execute(
            "SELECT COUNT(*) as c FROM properties"
        ).fetchone()["c"]
        active = self.db.conn.execute(
            "SELECT COUNT(*) as c FROM properties WHERE is_active = 1"
        ).fetchone()["c"]
        excluded = self.db.conn.execute(
            "SELECT COUNT(*) as c FROM exclusions"
        ).fetchone()["c"]
        today = date.today().isoformat()
        new_today = self.db.conn.execute(
            "SELECT COUNT(*) as c FROM properties WHERE first_seen_date = ?",
            (today,),
        ).fetchone()["c"]
        reduced = self.db.conn.execute(
            """SELECT COUNT(DISTINCT property_id) as c FROM price_history
               WHERE change_amount < 0"""
        ).fetchone()["c"]

        return {
            "total": total,
            "active": active,
            "excluded": excluded,
            "new_today": new_today,
            "reduced": reduced,
        }

    def upsert_enrichment(self, enrichment: dict) -> None:
        """Insert or replace enrichment data for a property."""
        prop_id = enrichment["property_id"]

        # Build dynamic upsert — only columns present in the dict
        cols = [k for k in enrichment if k != "property_id"]
        if not cols:
            return

        # Check if row exists
        existing = self.db.conn.execute(
            "SELECT id FROM enrichment_data WHERE property_id = ?", (prop_id,)
        ).fetchone()

        if existing:
            set_clause = ", ".join(f"{c} = ?" for c in cols)
            vals = [enrichment[c] for c in cols] + [prop_id]
            self.db.conn.execute(
                f"UPDATE enrichment_data SET {set_clause} WHERE property_id = ?",
                vals,
            )
        else:
            all_cols = ["property_id"] + cols
            placeholders = ", ".join("?" for _ in all_cols)
            vals = [prop_id] + [enrichment[c] for c in cols]
            self.db.conn.execute(
                f"INSERT INTO enrichment_data ({', '.join(all_cols)}) VALUES ({placeholders})",
                vals,
            )
        self.db.conn.commit()

    def get_enrichment(self, prop_id: int) -> dict | None:
        """Get enrichment data for a property."""
        row = self.db.conn.execute(
            "SELECT * FROM enrichment_data WHERE property_id = ?", (prop_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_properties_needing_enrichment(self) -> list[dict]:
        """Get active properties that have coords but incomplete enrichment data."""
        rows = self.db.conn.execute(
            """SELECT p.id, p.url, p.address, p.postcode, p.latitude, p.longitude
               FROM properties p
               LEFT JOIN enrichment_data e ON p.id = e.property_id
               WHERE p.is_active = 1
               AND p.latitude IS NOT NULL
               AND (e.property_id IS NULL
                    OR e.crime_summary IS NULL
                    OR e.nearest_supermarket_name IS NULL)
               ORDER BY p.first_seen_date DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def log_run(
        self,
        run_type: str,
        properties_found: int = 0,
        new_properties: int = 0,
        updated_properties: int = 0,
        removed_properties: int = 0,
        qualifying_count: int = 0,
        duration_seconds: float = 0,
        errors: list = None,
    ):
        """Log a run in the run_log table."""
        self.db.conn.execute(
            """INSERT INTO run_log (
                run_date, run_type, properties_found, new_properties,
                updated_properties, removed_properties, qualifying_count,
                duration_seconds, errors
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(),
                run_type,
                properties_found,
                new_properties,
                updated_properties,
                removed_properties,
                qualifying_count,
                duration_seconds,
                json.dumps(errors or []),
            ),
        )
        self.db.conn.commit()

    # --- Favourites ---

    def add_favourite(self, property_id: int, notes: str = "") -> bool:
        """Add property to favourites. Returns True if added, False if already exists."""
        try:
            self.db.conn.execute(
                "INSERT OR IGNORE INTO favourites (property_id, notes) VALUES (?, ?)",
                (property_id, notes),
            )
            self.db.conn.commit()
            return self.db.conn.total_changes > 0
        except Exception:
            return False

    def remove_favourite(self, property_id: int) -> bool:
        """Remove property from favourites."""
        self.db.conn.execute(
            "DELETE FROM favourites WHERE property_id = ?", (property_id,)
        )
        self.db.conn.commit()
        return self.db.conn.total_changes > 0

    def is_favourite(self, property_id: int) -> bool:
        row = self.db.conn.execute(
            "SELECT 1 FROM favourites WHERE property_id = ?", (property_id,)
        ).fetchone()
        return row is not None

    def get_favourites(self) -> list[dict]:
        """Get all favourited property IDs with notes."""
        rows = self.db.conn.execute(
            """SELECT p.*, f.notes as favourite_notes, f.added_at as favourite_added_at
               FROM properties p
               INNER JOIN favourites f ON p.id = f.property_id
               WHERE p.is_active = 1
               ORDER BY f.added_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_favourite_ids(self) -> set[int]:
        rows = self.db.conn.execute("SELECT property_id FROM favourites").fetchall()
        return {r[0] for r in rows}

    # --- Exclusions ---

    def exclude_property(self, property_id: int, reason: str = "Manually checked") -> bool:
        """Exclude a property from reports."""
        try:
            self.db.conn.execute(
                "INSERT OR IGNORE INTO exclusions (property_id, reason) VALUES (?, ?)",
                (property_id, reason),
            )
            self.db.conn.commit()
            return self.db.conn.total_changes > 0
        except Exception:
            return False

    def unexclude_property(self, property_id: int) -> bool:
        """Remove exclusion."""
        self.db.conn.execute(
            "DELETE FROM exclusions WHERE property_id = ?", (property_id,)
        )
        self.db.conn.commit()
        return self.db.conn.total_changes > 0

    def is_excluded(self, property_id: int) -> bool:
        row = self.db.conn.execute(
            "SELECT 1 FROM exclusions WHERE property_id = ?", (property_id,)
        ).fetchone()
        return row is not None

    def get_excluded_ids(self) -> set[int]:
        rows = self.db.conn.execute("SELECT property_id FROM exclusions").fetchall()
        return {r[0] for r in rows}

    # --- Notes ---

    def save_note(self, property_id: int, note_text: str) -> None:
        """Save or update a note for a property."""
        self.db.conn.execute(
            """INSERT INTO property_notes (property_id, note_text, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(property_id) DO UPDATE SET
                 note_text = excluded.note_text,
                 updated_at = datetime('now')""",
            (property_id, note_text),
        )
        self.db.conn.commit()

    def get_note(self, property_id: int) -> str:
        """Get note text for a property. Returns empty string if none."""
        row = self.db.conn.execute(
            "SELECT note_text FROM property_notes WHERE property_id = ?",
            (property_id,),
        ).fetchone()
        return row["note_text"] if row else ""

    def get_all_notes(self) -> dict[int, str]:
        """Get all notes as {property_id: note_text}."""
        rows = self.db.conn.execute(
            "SELECT property_id, note_text FROM property_notes WHERE note_text != ''"
        ).fetchall()
        return {r["property_id"]: r["note_text"] for r in rows}

    # --- Tracking Status ---

    def set_tracking_status(self, property_id: int, status: str) -> None:
        """Set tracking status for a property."""
        self.db.conn.execute(
            """INSERT INTO property_tracking (property_id, status, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(property_id) DO UPDATE SET
                 status = excluded.status,
                 updated_at = datetime('now')""",
            (property_id, status),
        )
        self.db.conn.commit()

    def get_tracking_status(self, property_id: int) -> str:
        """Get tracking status for a property. Returns 'new' if not set."""
        row = self.db.conn.execute(
            "SELECT status FROM property_tracking WHERE property_id = ?",
            (property_id,),
        ).fetchone()
        return row["status"] if row else "new"

    def get_all_tracking_statuses(self) -> dict[int, str]:
        """Get all tracking statuses as {property_id: status}."""
        rows = self.db.conn.execute(
            "SELECT property_id, status FROM property_tracking"
        ).fetchall()
        return {r["property_id"]: r["status"] for r in rows}

    # --- Viewings ---

    def add_viewing(self, property_id: int, viewing_date: str, viewing_time: str = "", notes: str = "") -> int:
        """Add a viewing. Returns the new viewing ID."""
        cur = self.db.conn.execute(
            """INSERT INTO viewings (property_id, viewing_date, viewing_time, notes)
               VALUES (?, ?, ?, ?)""",
            (property_id, viewing_date, viewing_time, notes),
        )
        self.db.conn.commit()
        return cur.lastrowid

    def update_viewing(self, viewing_id: int, viewing_date: str, viewing_time: str, status: str, notes: str) -> None:
        self.db.conn.execute(
            """UPDATE viewings SET viewing_date=?, viewing_time=?, status=?, notes=?, updated_at=datetime('now')
               WHERE id=?""",
            (viewing_date, viewing_time, status, notes, viewing_id),
        )
        self.db.conn.commit()

    def delete_viewing(self, viewing_id: int) -> None:
        self.db.conn.execute("DELETE FROM viewings WHERE id=?", (viewing_id,))
        self.db.conn.commit()

    def get_all_viewings(self) -> list[dict]:
        """Return all viewings joined with basic property info, sorted by date."""
        rows = self.db.conn.execute(
            """SELECT v.id, v.property_id, v.viewing_date, v.viewing_time, v.status, v.notes,
                      p.address, p.price, p.portal_id, p.agent_name, p.url
               FROM viewings v
               JOIN properties p ON p.id = v.property_id
               ORDER BY v.viewing_date ASC, v.viewing_time ASC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_viewing(self, viewing_id: int) -> dict | None:
        row = self.db.conn.execute("SELECT * FROM viewings WHERE id=?", (viewing_id,)).fetchone()
        return dict(row) if row else None
