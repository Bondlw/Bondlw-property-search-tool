"""CLI integration tests using Click's test runner.

Tests the Click commands via CliRunner — no real HTTP calls or DB writes.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_config(base_config):
    config = base_config.copy()
    config["search_areas"] = {
        "primary": [
            {"name": "Chatham", "lat": 51.37, "lng": 0.53, "rightmove_id": "REGION^123"},
        ],
    }
    config["max_radius_miles"] = 15
    config["notifications"] = {}
    return config


# ── init command ──────────────────────────────────────────────────────────

class TestInitCommand:
    def test_init_creates_database(self, runner):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            with patch("src.cli.get_db_path", return_value=db_path):
                with patch("src.cli.load_config", return_value={}):
                    result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert "initialised" in result.output.lower()
            assert os.path.exists(db_path)


# ── run command ───────────────────────────────────────────────────────────

class TestRunCommand:
    def test_dry_run_flag(self, runner, mock_config):
        """--dry-run should not write to database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            with patch("src.cli.get_db_path", return_value=db_path):
                with patch("src.cli.load_config", return_value=mock_config):
                    # Mock the scraper to return empty results
                    with patch("src.cli.RightmoveScraper") as mock_scraper_cls:
                        mock_scraper = MagicMock()
                        mock_scraper.search.return_value = []
                        mock_scraper_cls.return_value = mock_scraper
                        result = runner.invoke(cli, ["run", "--dry-run"])
            assert result.exit_code == 0


# ── report command ────────────────────────────────────────────────────────

class TestReportCommand:
    def test_report_generates_output(self, runner, mock_config):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            # Create and init the DB first
            from src.storage.database import Database
            with Database(db_path) as db:
                db.init_schema()

            with patch("src.cli.get_db_path", return_value=db_path):
                with patch("src.cli.load_config", return_value=mock_config):
                    with patch("webbrowser.open"):
                        result = runner.invoke(cli, ["report"])
            assert result.exit_code == 0
            assert "no active properties" in result.output.lower()


# ── search command ────────────────────────────────────────────────────────

class TestSearchCommand:
    def test_search_with_no_results(self, runner, mock_config):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            from src.storage.database import Database
            with Database(db_path) as db:
                db.init_schema()

            with patch("src.cli.get_db_path", return_value=db_path):
                with patch("src.cli.load_config", return_value=mock_config):
                    with patch("src.cli.RightmoveScraper") as mock_scraper_cls:
                        mock_scraper = MagicMock()
                        mock_scraper.search.return_value = []
                        mock_scraper_cls.return_value = mock_scraper
                        result = runner.invoke(cli, ["search"])
            assert result.exit_code == 0


# ── help output ───────────────────────────────────────────────────────────

class TestHelpOutput:
    def test_main_help(self, runner):
        with patch("src.cli.load_config", return_value={}):
            result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Property Search Tool" in result.output

    def test_run_help(self, runner):
        with patch("src.cli.load_config", return_value={}):
            result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--max-properties" in result.output

    def test_init_help(self, runner):
        with patch("src.cli.load_config", return_value={}):
            result = runner.invoke(cli, ["init", "--help"])
        assert result.exit_code == 0
