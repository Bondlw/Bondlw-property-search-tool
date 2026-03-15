"""SQLite database connection manager and schema creation."""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 4

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

CREATE INDEX IF NOT EXISTS idx_properties_postcode ON properties(postcode);
CREATE INDEX IF NOT EXISTS idx_properties_portal_id ON properties(portal, portal_id);
CREATE INDEX IF NOT EXISTS idx_properties_url_norm ON properties(url_normalised);
CREATE INDEX IF NOT EXISTS idx_properties_active ON properties(is_active);
CREATE INDEX IF NOT EXISTS idx_properties_first_seen ON properties(first_seen_date);
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
        self.conn.commit()

    def _migrate_v2(self):
        """Add images column and favourites table."""
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
        """Add supermarket aggregate columns to enrichment_data and new property columns."""
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
        """Add viewings table."""
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

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.init_schema()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
