"""Integration tests for PropertyRepository backed by real SQLite."""

import tempfile
from pathlib import Path

import pytest

from src.storage.database import Database
from src.storage.models import RawListing
from src.storage.repository import PropertyRepository


@pytest.fixture
def db():
    """Provide a fresh in-memory database with schema initialised."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        database = Database(db_path)
        database.init_schema()
        yield database
        database.close()


@pytest.fixture
def repo(db):
    """Return a PropertyRepository backed by the test database."""
    return PropertyRepository(db)


def _make_listing(**overrides) -> RawListing:
    """Build a RawListing with sensible defaults; any field can be overridden."""
    defaults = dict(
        portal="rightmove",
        portal_id="12345",
        url="https://www.rightmove.co.uk/property/12345",
        title="2 Bed Flat",
        price=175000,
        address="1 Test Road, TN1 1AA",
        postcode="TN1 1AA",
        property_type="Flat",
    )
    defaults.update(overrides)
    return RawListing(**defaults)


# ──────────────────────────────────────────────
# Insert / Exists / Lookup
# ──────────────────────────────────────────────

class TestInsertAndLookup:

    def test_insert_returns_id(self, repo):
        listing = _make_listing()
        pid = repo.insert_property(listing, "rightmove.co.uk/property/12345")
        assert isinstance(pid, int) and pid > 0

    def test_property_exists_after_insert(self, repo):
        listing = _make_listing()
        repo.insert_property(listing, "rightmove.co.uk/property/12345")
        assert repo.property_exists("rightmove", "12345") is not None

    def test_property_not_exists_before_insert(self, repo):
        assert repo.property_exists("rightmove", "99999") is None

    def test_find_by_normalised_url(self, repo):
        listing = _make_listing()
        pid = repo.insert_property(listing, "rightmove.co.uk/property/12345")
        found = repo.find_by_normalised_url("rightmove.co.uk/property/12345")
        assert found == pid

    def test_get_property_returns_all_fields(self, repo):
        listing = _make_listing(bedrooms=3, tenure="freehold")
        pid = repo.insert_property(listing, "rightmove.co.uk/property/12345")
        prop = repo.get_property(pid)
        assert prop is not None
        assert prop["bedrooms"] == 3
        assert prop["tenure"] == "freehold"
        assert prop["is_active"] == 1

    def test_duplicate_portal_id_raises(self, repo):
        listing = _make_listing()
        repo.insert_property(listing, "rightmove.co.uk/property/12345")
        with pytest.raises(Exception):
            repo.insert_property(listing, "rightmove.co.uk/property/12345")

    def test_initial_price_history_recorded(self, repo):
        listing = _make_listing(price=200000)
        pid = repo.insert_property(listing, "rightmove.co.uk/property/12345")
        history = repo.get_price_history(pid)
        assert len(history) == 1
        assert history[0]["price"] == 200000


# ──────────────────────────────────────────────
# Update Property (price changes)
# ──────────────────────────────────────────────

class TestUpdateProperty:

    def test_same_price_returns_false(self, repo):
        listing = _make_listing(price=175000)
        pid = repo.insert_property(listing, "norm-url")
        changed = repo.update_property(pid, _make_listing(price=175000))
        assert changed is False

    def test_different_price_returns_true(self, repo):
        listing = _make_listing(price=175000)
        pid = repo.insert_property(listing, "norm-url")
        changed = repo.update_property(pid, _make_listing(price=170000))
        assert changed is True

    def test_price_change_adds_history(self, repo):
        listing = _make_listing(price=175000)
        pid = repo.insert_property(listing, "norm-url")
        repo.update_property(pid, _make_listing(price=170000))
        history = repo.get_price_history(pid)
        assert len(history) == 2
        assert history[-1]["price"] == 170000

    def test_price_reduction_sets_flag(self, repo):
        listing = _make_listing(price=175000)
        pid = repo.insert_property(listing, "norm-url")
        repo.update_property(pid, _make_listing(price=165000))
        prop = repo.get_property(pid)
        assert prop["price_reduced"] == 1

    def test_price_increase_no_reduction_flag(self, repo):
        listing = _make_listing(price=175000)
        pid = repo.insert_property(listing, "norm-url")
        repo.update_property(pid, _make_listing(price=185000))
        prop = repo.get_property(pid)
        assert prop["price_reduced"] == 0


# ──────────────────────────────────────────────
# Favourites
# ──────────────────────────────────────────────

class TestFavourites:

    def test_toggle_add(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        result = repo.toggle_favourite(pid)
        assert result is True
        assert repo.is_favourite(pid)

    def test_toggle_remove(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        repo.toggle_favourite(pid)  # add
        result = repo.toggle_favourite(pid)  # remove
        assert result is False
        assert not repo.is_favourite(pid)

    def test_add_favourite_idempotent(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        repo.add_favourite(pid, "Great place")
        repo.add_favourite(pid, "Updated notes")
        assert repo.is_favourite(pid)

    def test_get_favourite_ids(self, repo):
        p1 = repo.insert_property(_make_listing(portal_id="a"), "url-a")
        p2 = repo.insert_property(_make_listing(portal_id="b"), "url-b")
        repo.add_favourite(p1)
        repo.add_favourite(p2)
        ids = repo.get_favourite_ids()
        assert ids == {p1, p2}


# ──────────────────────────────────────────────
# Exclusions
# ──────────────────────────────────────────────

class TestExclusions:

    def test_exclude_property(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        repo.exclude_property(pid, "Too expensive")
        assert repo.is_excluded(pid)

    def test_unexclude_property(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        repo.exclude_property(pid, "Too expensive")
        repo.unexclude_property(pid)
        assert not repo.is_excluded(pid)

    def test_excluded_ids(self, repo):
        p1 = repo.insert_property(_make_listing(portal_id="a"), "url-a")
        repo.exclude_property(p1, "reason")
        assert p1 in repo.get_excluded_ids()


# ──────────────────────────────────────────────
# Notes
# ──────────────────────────────────────────────

class TestNotes:

    def test_save_and_get_note(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        repo.save_note(pid, "Good location near station")
        assert repo.get_note(pid) == "Good location near station"

    def test_update_existing_note(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        repo.save_note(pid, "First note")
        repo.save_note(pid, "Updated note")
        assert repo.get_note(pid) == "Updated note"

    def test_get_note_returns_empty_for_missing(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        assert repo.get_note(pid) == ""

    def test_get_all_notes(self, repo):
        p1 = repo.insert_property(_make_listing(portal_id="a"), "url-a")
        p2 = repo.insert_property(_make_listing(portal_id="b"), "url-b")
        repo.save_note(p1, "Note A")
        repo.save_note(p2, "Note B")
        notes = repo.get_all_notes()
        assert notes[p1] == "Note A"
        assert notes[p2] == "Note B"


# ──────────────────────────────────────────────
# Enrichment
# ──────────────────────────────────────────────

class TestEnrichment:

    def test_upsert_and_get_enrichment(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        repo.upsert_enrichment({
            "property_id": pid,
            "nearest_station_name": "Tunbridge Wells",
            "nearest_station_walk_min": 12,
        })
        enrichment = repo.get_enrichment(pid)
        assert enrichment is not None
        assert enrichment["nearest_station_name"] == "Tunbridge Wells"
        assert enrichment["nearest_station_walk_min"] == 12

    def test_upsert_overwrites_existing(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        repo.upsert_enrichment({"property_id": pid, "nearest_station_walk_min": 10})
        repo.upsert_enrichment({"property_id": pid, "nearest_station_walk_min": 8})
        enrichment = repo.get_enrichment(pid)
        assert enrichment["nearest_station_walk_min"] == 8

    def test_get_enrichment_missing_returns_none(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        assert repo.get_enrichment(pid) is None


# ──────────────────────────────────────────────
# Mark Inactive
# ──────────────────────────────────────────────

class TestMarkInactive:

    def test_mark_inactive(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        repo.mark_inactive(pid, status="removed")
        prop = repo.get_property(pid)
        assert prop["is_active"] == 0
        assert prop["status"] == "removed"

    def test_inactive_excluded_from_active_list(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        repo.mark_inactive(pid)
        active = repo.get_active_properties()
        assert not any(p["id"] == pid for p in active)


# ──────────────────────────────────────────────
# Stats
# ──────────────────────────────────────────────

class TestStats:

    def test_stats_returns_expected_keys(self, repo):
        stats = repo.get_stats()
        assert "total" in stats
        assert "active" in stats

    def test_stats_counts_active(self, repo):
        p1 = repo.insert_property(_make_listing(portal_id="a"), "a")
        p2 = repo.insert_property(_make_listing(portal_id="b"), "b")
        repo.mark_inactive(p2)
        stats = repo.get_stats()
        assert stats["active"] == 1


# ──────────────────────────────────────────────
# Tracking Status
# ──────────────────────────────────────────────

class TestTracking:

    def test_set_and_get_tracking_status(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        repo.set_tracking_status(pid, "viewing_booked")
        assert repo.get_tracking_status(pid) == "viewing_booked"

    def test_default_tracking_status(self, repo):
        pid = repo.insert_property(_make_listing(), "url")
        assert repo.get_tracking_status(pid) == "new"

    def test_get_all_tracking_statuses(self, repo):
        p1 = repo.insert_property(_make_listing(portal_id="a"), "a")
        p2 = repo.insert_property(_make_listing(portal_id="b"), "b")
        repo.set_tracking_status(p1, "contacted")
        repo.set_tracking_status(p2, "offer_made")
        statuses = repo.get_all_tracking_statuses()
        assert statuses[p1] == "contacted"
        assert statuses[p2] == "offer_made"


# ──────────────────────────────────────────────
# Database Backup
# ──────────────────────────────────────────────

class TestDatabaseBackup:

    def test_backup_creates_file(self, db):
        import tempfile
        with tempfile.TemporaryDirectory() as backup_dir:
            result = db.backup(backup_dir)
            assert result is not None
            assert Path(result).exists()

    def test_backup_retention_keeps_max_5(self, db):
        import tempfile
        with tempfile.TemporaryDirectory() as backup_dir:
            # Create 7 backups — only 5 should remain
            for _ in range(7):
                db.backup(backup_dir)
            backup_files = list(Path(backup_dir).glob("*.db"))
            assert len(backup_files) <= 5
