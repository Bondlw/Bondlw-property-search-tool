"""Integration tests for the report API server."""

import json
import tempfile
import threading
from http.server import HTTPServer
from pathlib import Path
from functools import partial
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from src.storage.database import Database
from src.storage.models import RawListing
from src.storage.repository import PropertyRepository
from src.server.report_server import ReportAPIHandler


@pytest.fixture
def server_env():
    """Spin up a real HTTP server backed by a temp SQLite database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Database
        db_path = str(Path(tmpdir) / "test.db")
        database = Database(db_path)
        database.init_schema()
        repo = PropertyRepository(database)

        # Insert a property so endpoints have data to work with
        listing = RawListing(
            portal="rightmove",
            portal_id="99999",
            url="https://www.rightmove.co.uk/property/99999",
            title="Test Property",
            price=175000,
            address="1 Test Road",
            postcode="TN1 1AA",
            property_type="Flat",
        )
        prop_id = repo.insert_property(listing, "rightmove.co.uk/property/99999")

        # Report dir with a dummy report
        report_dir = Path(tmpdir) / "reports"
        report_dir.mkdir()
        (report_dir / "daily_report.html").write_text("<html>test</html>", encoding="utf-8")

        handler = partial(
            ReportAPIHandler,
            report_dir=str(report_dir),
            db_path=db_path,
        )
        server = HTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        yield {
            "base_url": f"http://127.0.0.1:{port}",
            "prop_id": prop_id,
            "db": database,
            "repo": repo,
        }

        server.shutdown()
        database.close()


def _api(url: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    """Make an API request and return (status_code, json_body)."""
    data = json.dumps(body).encode("utf-8") if body else None
    req = Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except HTTPError as err:
        return err.code, json.loads(err.read())


class TestFavouriteEndpoints:

    def test_favourite_and_unfavourite(self, server_env):
        base = server_env["base_url"]
        pid = server_env["prop_id"]

        # Favourite
        status, data = _api(f"{base}/api/favourite/{pid}", "POST")
        assert status == 200

        # Verify via repo
        assert server_env["repo"].is_favourite(pid)

        # Unfavourite
        status, data = _api(f"{base}/api/unfavourite/{pid}", "POST")
        assert status == 200
        assert not server_env["repo"].is_favourite(pid)


class TestExcludeEndpoints:

    def test_exclude_and_unexclude(self, server_env):
        base = server_env["base_url"]
        pid = server_env["prop_id"]

        status, data = _api(
            f"{base}/api/exclude/{pid}", "POST",
            {"reason": "Too far from station"},
        )
        assert status == 200
        assert server_env["repo"].is_excluded(pid)

        status, data = _api(f"{base}/api/unexclude/{pid}", "POST")
        assert status == 200
        assert not server_env["repo"].is_excluded(pid)


class TestNoteEndpoints:

    def test_save_and_get_note(self, server_env):
        base = server_env["base_url"]
        pid = server_env["prop_id"]

        _api(f"{base}/api/note/{pid}", "POST", {"text": "Great garden"})
        status, data = _api(f"{base}/api/note/{pid}", "GET")
        assert status == 200
        assert data["text"] == "Great garden"

    def test_note_too_long_returns_400(self, server_env):
        base = server_env["base_url"]
        pid = server_env["prop_id"]
        long_note = "x" * 5001
        status, data = _api(f"{base}/api/note/{pid}", "POST", {"text": long_note})
        assert status == 400

    def test_get_all_notes(self, server_env):
        base = server_env["base_url"]
        pid = server_env["prop_id"]
        _api(f"{base}/api/note/{pid}", "POST", {"text": "A note"})
        status, data = _api(f"{base}/api/notes", "GET")
        assert status == 200
        assert str(pid) in data["notes"] or pid in [int(k) for k in data["notes"]]


class TestTrackingEndpoints:

    def test_set_and_get_tracking(self, server_env):
        base = server_env["base_url"]
        pid = server_env["prop_id"]

        _api(f"{base}/api/tracking/{pid}", "POST", {"status": "viewing_booked"})
        status, data = _api(f"{base}/api/trackings", "GET")
        assert status == 200


class TestInputValidation:

    def test_oversized_payload_returns_413(self, server_env):
        base = server_env["base_url"]
        pid = server_env["prop_id"]
        # Build a payload larger than MAX_BODY_SIZE (50KB)
        big_payload = {"text": "a" * 60_000}
        status, data = _api(f"{base}/api/note/{pid}", "POST", big_payload)
        assert status == 413

    def test_invalid_json_returns_400(self, server_env):
        base = server_env["base_url"]
        pid = server_env["prop_id"]
        # Send raw non-JSON bytes
        url = f"{base}/api/note/{pid}"
        req = Request(url, data=b"not-valid-json", method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Content-Length", "14")
        try:
            with urlopen(req) as resp:
                status = resp.status
                body = json.loads(resp.read())
        except HTTPError as err:
            status = err.code
            body = json.loads(err.read())
        assert status == 400
        assert "Invalid JSON" in body.get("error", "")

    def test_not_found_returns_404(self, server_env):
        base = server_env["base_url"]
        status, data = _api(f"{base}/api/nonexistent", "POST", {})
        assert status == 404


class TestCORSPreflight:

    def test_options_returns_204(self, server_env):
        base = server_env["base_url"]
        req = Request(f"{base}/api/favourite/1", method="OPTIONS")
        with urlopen(req) as resp:
            assert resp.status == 204
            assert "GET" in resp.headers.get("Access-Control-Allow-Methods", "")
