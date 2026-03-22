"""SQLite database connection manager and schema creation."""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 5

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portal TEXT NOT NULL,
    portal_id TEXT NOT NULL,
    url TEXT NOT NULL,
    url_normalised TEXT NOT NULL,
    title TEXT,
    price INTEGER NOT NULL,
    address TEXT,
    postcode TEXT,
    property_type TEXT,
    bedrooms INTEGER,
    bathrooms INTEGER,
    tenure TEXT,
    lease_years INTEGER,
    service_charge_pa INTEGER,
    ground_rent_pa INTEGER,
    council_tax_band TEXT,
    epc_rating TEXT,
    description TEXT,
    key_features TEXT,
    images TEXT,
    floorplan_urls TEXT,
    video_url TEXT,
    brochure_url TEXT,
    rooms TEXT,
    size_sqft INTEGER,
    price_reduced INTEGER DEFAULT 0,
    agent_name TEXT,
    latitude REAL,
    longitude REAL,
    first_seen_date TEXT NOT NULL,
    last_seen_date TEXT NOT NULL,
    first_listed_date TEXT,
    days_on_market INTEGER,
    is_active INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(portal, portal_id)
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    price INTEGER NOT NULL,
    recorded_date TEXT NOT NULL,
    change_amount INTEGER,
    change_pct REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS enrichment_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id) UNIQUE,
    nearest_station_name TEXT,
    nearest_station_distance_m REAL,
    nearest_station_walk_min INTEGER,
    nearest_lidl_distance_m REAL,
    nearest_lidl_walk_min INTEGER,
    nearest_aldi_distance_m REAL,
    nearest_aldi_walk_min INTEGER,
    nearest_supermarket_name TEXT,
    nearest_supermarket_distance_m REAL,
    nearest_supermarket_walk_min INTEGER,
    crime_summary TEXT,
    crime_safety_score REAL,
    crime_data_date TEXT,
    commute_to_london_min INTEGER,
    commute_to_maidstone_min INTEGER,
    annual_season_ticket INTEGER,
    council_tax_band_verified TEXT,
    council_tax_annual_estimate INTEGER,
    flood_zone INTEGER,
    broadband_speed_mbps REAL,
    avg_sold_price_nearby INTEGER,
    enriched_at TEXT DEFAULT (datetime('now')),
    crime_checked_at TEXT,
    walkability_checked_at TEXT
);

CREATE TABLE IF NOT EXISTS gate_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    gate_name TEXT NOT NULL,
    passed INTEGER NOT NULL,
    reason TEXT,
    checked_at TEXT DEFAULT (datetime('now')),
    UNIQUE(property_id, gate_name)
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id) UNIQUE,
    financial_fit REAL,
    crime_safety REAL,
    cost_predictability REAL,
    layout_livability REAL,
    walkability REAL,
    long_term_flexibility REAL,
    total_score REAL,
    scored_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS exclusions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id) UNIQUE,
    reason TEXT NOT NULL,
    excluded_at TEXT DEFAULT (datetime('now')),
    excluded_by TEXT DEFAULT 'user'
);

CREATE TABLE IF NOT EXISTS favourites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id) UNIQUE,
    notes TEXT,
    added_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    run_type TEXT NOT NULL,
    properties_found INTEGER,
    new_properties INTEGER,
    updated_properties INTEGER,
    removed_properties INTEGER,
    qualifying_count INTEGER,
    duration_seconds REAL,
    errors TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS search_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_name TEXT NOT NULL UNIQUE,
    area_type TEXT NOT NULL,
    rightmove_location_id TEXT,
    zoopla_area_slug TEXT,
    onthemarket_area_slug TEXT,
    latitude REAL,
    longitude REAL,
    is_active INTEGER DEFAULT 1,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS property_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id) UNIQUE,
    note_text TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS property_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id) UNIQUE,
    status TEXT NOT NULL DEFAULT 'new',
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS viewings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    viewing_date TEXT NOT NULL,
    viewing_time TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'scheduled',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_viewings_property ON viewings(property_id);
CREATE INDEX IF NOT EXISTS idx_viewings_date ON viewings(viewing_date);

CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    amount INTEGER NOT NULL,
    offer_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_offers_property ON offers(property_id);
CREATE INDEX IF NOT EXISTS idx_offers_status ON offers(status);

CREATE TABLE IF NOT EXISTS viewing_inspections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    viewing_id INTEGER NOT NULL REFERENCES viewings(id),
    property_id INTEGER NOT NULL REFERENCES properties(id),
    condition_score INTEGER DEFAULT 0,
    light_score INTEGER DEFAULT 0,
    noise_score INTEGER DEFAULT 0,
    parking TEXT DEFAULT '',
    storage TEXT DEFAULT '',
    pros TEXT DEFAULT '',
    cons TEXT DEFAULT '',
    would_offer INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(viewing_id)
);

CREATE INDEX IF NOT EXISTS idx_inspections_property ON viewing_inspections(property_id);

CREATE INDEX IF NOT EXISTS idx_properties_postcode ON properties(postcode);
CREATE INDEX IF NOT EXISTS idx_properties_portal_id ON properties(portal, portal_id);
CREATE INDEX IF NOT EXISTS idx_properties_url_norm ON properties(url_normalised);
CREATE INDEX IF NOT EXISTS idx_properties_active ON properties(is_active);
CREATE INDEX IF NOT EXISTS idx_properties_first_seen ON properties(first_seen_date);
CREATE INDEX IF NOT EXISTS idx_properties_active_first_seen ON properties(is_active, first_seen_date DESC);
CREATE INDEX IF NOT EXISTS idx_price_history_property ON price_history(property_id);
CREATE INDEX IF NOT EXISTS idx_price_history_date ON price_history(recorded_date);
"""


class Database:
    """SQLite database connection manager."""

    def __init__(self, db_path: str = "data/property_search.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def init_schema(self):
        """Create all tables and indexes, run migrations for existing DBs."""
        self.conn.executescript(SCHEMA_SQL)
        # Set schema version if not already set
        row = self.conn.execute(
            "SELECT version FROM schema_version LIMIT 1"
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
        else:
            current = row["version"]
            if current < 2:
                self._migrate_v2()
            if current < 3:
                self._migrate_v3()
            if current < 4:
                self._migrate_v4()
            if current < 5:
                self._migrate_v5()
        self.conn.commit()

    def _migrate_v2(self):
        """v2: Add images column and favourites table.

        - properties.images: store image URLs as JSON array for gallery display
        - favourites table: allow users to mark properties as favourites with notes
        """
        cols = [c[1] for c in self.conn.execute("PRAGMA table_info(properties)").fetchall()]
        if "images" not in cols:
            self.conn.execute("ALTER TABLE properties ADD COLUMN images TEXT")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS favourites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id INTEGER NOT NULL REFERENCES properties(id) UNIQUE,
                notes TEXT,
                added_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self.conn.execute("UPDATE schema_version SET version = 2")
        self.conn.commit()

    def _migrate_v3(self):
        """v3: Add supermarket aggregates and new property detail columns.

        - enrichment_data: nearest_supermarket_name/distance_m/walk_min — stores best
          supermarket across all chains (not just Lidl/Aldi)
        - properties: floorplan_urls, video_url, brochure_url, rooms — detail page
          data captured during listing detail fetch
        - properties.price_reduced: flag set when a price drop is detected vs. prior run
        """
        e_cols = {c[1] for c in self.conn.execute("PRAGMA table_info(enrichment_data)").fetchall()}
        for col, coltype in [
            ("nearest_supermarket_name", "TEXT"),
            ("nearest_supermarket_distance_m", "REAL"),
            ("nearest_supermarket_walk_min", "INTEGER"),
        ]:
            if col not in e_cols:
                self.conn.execute(f"ALTER TABLE enrichment_data ADD COLUMN {col} {coltype}")

        p_cols = {c[1] for c in self.conn.execute("PRAGMA table_info(properties)").fetchall()}
        for col, coltype in [
            ("floorplan_urls", "TEXT"),
            ("video_url", "TEXT"),
            ("brochure_url", "TEXT"),
            ("rooms", "TEXT"),
        ]:
            if col not in p_cols:
                self.conn.execute(f"ALTER TABLE properties ADD COLUMN {col} {coltype}")
        if "price_reduced" not in p_cols:
            self.conn.execute("ALTER TABLE properties ADD COLUMN price_reduced INTEGER DEFAULT 0")

        self.conn.execute("UPDATE schema_version SET version = 3")
        self.conn.commit()

    def _migrate_v4(self):
        """v4: Add viewings table for scheduling property viewings.

        - viewings: property_id, viewing_date, viewing_time, status (scheduled/completed/cancelled),
          notes. Indexed by property_id and date for fast lookups.
        """
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS viewings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id INTEGER NOT NULL REFERENCES properties(id),
                viewing_date TEXT NOT NULL,
                viewing_time TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'scheduled',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_viewings_property ON viewings(property_id);
            CREATE INDEX IF NOT EXISTS idx_viewings_date ON viewings(viewing_date);
        """)
        self.conn.execute("UPDATE schema_version SET version = 4")
        self.conn.commit()

    def _migrate_v5(self):
        """v5: Add offers tracking and post-viewing inspection records.

        - offers: track offers made on properties with amount, date, status
          (pending/accepted/rejected/withdrawn), and notes
        - viewing_inspections: post-viewing data linked to a viewing record —
          condition/light/noise scores (0-5), parking, storage, pros/cons text,
          and would_offer flag. UNIQUE on viewing_id (one inspection per viewing).
        """
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id INTEGER NOT NULL REFERENCES properties(id),
                amount INTEGER NOT NULL,
                offer_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_offers_property ON offers(property_id);
            CREATE INDEX IF NOT EXISTS idx_offers_status ON offers(status);
            CREATE TABLE IF NOT EXISTS viewing_inspections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                viewing_id INTEGER NOT NULL REFERENCES viewings(id),
                property_id INTEGER NOT NULL REFERENCES properties(id),
                condition_score INTEGER DEFAULT 0,
                light_score INTEGER DEFAULT 0,
                noise_score INTEGER DEFAULT 0,
                parking TEXT DEFAULT '',
                storage TEXT DEFAULT '',
                pros TEXT DEFAULT '',
                cons TEXT DEFAULT '',
                would_offer INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(viewing_id)
            );
            CREATE INDEX IF NOT EXISTS idx_inspections_property ON viewing_inspections(property_id);
        """)
        self.conn.execute("UPDATE schema_version SET version = 5")
        self.conn.commit()

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def backup(self, backup_dir: str | Path = "data/backups") -> str | None:
        """Create a SQLite backup using VACUUM INTO.

        Returns the backup file path, or None if backup failed.
        """
        from datetime import datetime

        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_path / f"property_search_{timestamp}.db"

        try:
            self.conn.execute(f"VACUUM INTO ?", (str(backup_file),))
            logger.info(f"Database backed up to {backup_file}")

            # Keep only the 5 most recent backups
            backups = sorted(backup_path.glob("property_search_*.db"), reverse=True)
            for old_backup in backups[5:]:
                old_backup.unlink()
                logger.debug(f"Removed old backup: {old_backup}")

            return str(backup_file)
        except sqlite3.Error as exc:
            logger.error(f"Backup failed: {exc}")
            return None

    def __enter__(self):
        self.init_schema()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
