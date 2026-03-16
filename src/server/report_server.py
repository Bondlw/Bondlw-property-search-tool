"""Minimal local HTTP server for report interactivity.

Serves the latest report and provides API endpoints for
favourite/exclude actions from the browser.

Usage: python -m src serve [--port 8765]
"""

import json
import logging
import os
import re
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from ..storage.database import Database
from ..storage.repository import PropertyRepository

logger = logging.getLogger(__name__)


def get_db_path():
    return os.environ.get("PROPERTY_DB", "data/property_search.db")


class ReportAPIHandler(SimpleHTTPRequestHandler):
    """Handles static file serving and API endpoints."""

    def __init__(self, *args, report_dir: str = "", db_path: str = "", **kwargs):
        self.report_dir = report_dir
        self.db_path = db_path
        super().__init__(*args, directory=report_dir, **kwargs)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # POST /api/favourite/<id>
        match = re.match(r"^/api/favourite/(\d+)$", path)
        if match:
            self._handle_favourite(int(match.group(1)))
            return

        # POST /api/exclude/<id>
        match = re.match(r"^/api/exclude/(\d+)$", path)
        if match:
            body = self._read_body()
            reason = body.get("reason", "Manually checked") if body else "Manually checked"
            self._handle_exclude(int(match.group(1)), reason)
            return

        # POST /api/unfavourite/<id>
        match = re.match(r"^/api/unfavourite/(\d+)$", path)
        if match:
            self._handle_unfavourite(int(match.group(1)))
            return

        # POST /api/unexclude/<id>
        match = re.match(r"^/api/unexclude/(\d+)$", path)
        if match:
            self._handle_unexclude(int(match.group(1)))
            return

        # POST /api/note/<id>
        match = re.match(r"^/api/note/(\d+)$", path)
        if match:
            body = self._read_body()
            note_text = body.get("text", "") if body else ""
            self._handle_save_note(int(match.group(1)), note_text)
            return

        # POST /api/tracking/<id>
        match = re.match(r"^/api/tracking/(\d+)$", path)
        if match:
            body = self._read_body()
            status = body.get("status", "new") if body else "new"
            self._handle_set_tracking(int(match.group(1)), status)
            return

        # POST /api/regenerate — re-run the report generator
        if path == "/api/regenerate":
            self._handle_regenerate()
            return

        # POST /api/viewing — add a new viewing
        if path == "/api/viewing":
            body = self._read_body() or {}
            self._handle_add_viewing(body)
            return

        # PUT /api/viewing/<id> — update a viewing
        match = re.match(r"^/api/viewing/(\d+)$", path)
        if match and self.command == 'POST' and self.headers.get('X-Method') == 'PUT':
            body = self._read_body() or {}
            self._handle_update_viewing(int(match.group(1)), body)
            return

        # DELETE /api/viewing/<id> — delete a viewing
        match = re.match(r"^/api/viewing/(\d+)/delete$", path)
        if match:
            self._handle_delete_viewing(int(match.group(1)))
            return

        # POST /api/enquiry/<id> — auto-fill Rightmove contact form via Playwright
        match = re.match(r"^/api/enquiry/(\d+)$", path)
        if match:
            self._handle_enquiry(int(match.group(1)))
            return

        self._json_response(404, {"error": "Not found"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        # DELETE /api/viewing/<prop_id>
        match = re.match(r"^/api/viewing/(\d+)$", path)
        if match:
            self._handle_delete_viewing(int(match.group(1)))
            return
        self._json_response(404, {"error": "Not found"})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # GET /api/status/<id>
        match = re.match(r"^/api/status/(\d+)$", path)
        if match:
            self._handle_status(int(match.group(1)))
            return

        # GET /api/statuses — bulk status for all properties
        if path == "/api/statuses":
            self._handle_all_statuses()
            return

        # GET /api/note/<id>
        match = re.match(r"^/api/note/(\d+)$", path)
        if match:
            self._handle_get_note(int(match.group(1)))
            return

        # GET /api/notes — all notes
        if path == "/api/notes":
            self._handle_all_notes()
            return

        # GET /api/trackings — all tracking statuses
        if path == "/api/trackings":
            self._handle_all_trackings()
            return

        # GET /api/viewings — all viewings
        if path == "/api/viewings":
            self._handle_all_viewings()
            return

        # GET / — serve latest report
        if path == "/" or path == "":
            self._serve_latest_report()
            return

        # Default: serve static files from report dir
        super().do_GET()

    def _read_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        if length:
            try:
                return json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _json_response(self, status: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _handle_favourite(self, prop_id: int):
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            if repo.is_favourite(prop_id):
                repo.remove_favourite(prop_id)
                self._json_response(200, {"action": "removed", "id": prop_id})
            else:
                repo.add_favourite(prop_id)
                self._json_response(200, {"action": "added", "id": prop_id})

    def _handle_unfavourite(self, prop_id: int):
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            repo.remove_favourite(prop_id)
            self._json_response(200, {"action": "removed", "id": prop_id})

    def _handle_exclude(self, prop_id: int, reason: str):
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            repo.exclude_property(prop_id, reason)
            self._json_response(200, {"action": "excluded", "id": prop_id})

    def _handle_unexclude(self, prop_id: int):
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            repo.unexclude_property(prop_id)
            self._json_response(200, {"action": "unexcluded", "id": prop_id})

    def _handle_status(self, prop_id: int):
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            self._json_response(200, {
                "id": prop_id,
                "favourite": repo.is_favourite(prop_id),
                "excluded": repo.is_excluded(prop_id),
            })

    def _handle_all_statuses(self):
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            fav_ids = repo.get_favourite_ids()
            excl_ids = repo.get_excluded_ids()
            self._json_response(200, {
                "favourites": list(fav_ids),
                "excluded": list(excl_ids),
            })

    def _handle_save_note(self, prop_id: int, text: str):
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            repo.save_note(prop_id, text)
            self._json_response(200, {"action": "saved", "id": prop_id})

    def _handle_get_note(self, prop_id: int):
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            note = repo.get_note(prop_id)
            self._json_response(200, {"id": prop_id, "text": note})

    def _handle_all_notes(self):
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            notes = repo.get_all_notes()
            self._json_response(200, {"notes": {str(k): v for k, v in notes.items()}})

    def _handle_set_tracking(self, prop_id: int, status: str):
        valid_statuses = {"new", "reviewing", "contacted", "viewing_booked", "viewed", "offer_made", "rejected", "archived"}
        if status not in valid_statuses:
            self._json_response(400, {"error": f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}"})
            return
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            repo.set_tracking_status(prop_id, status)
            self._json_response(200, {"action": "updated", "id": prop_id, "status": status})

    def _handle_all_trackings(self):
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            statuses = repo.get_all_tracking_statuses()
            self._json_response(200, {"trackings": {str(k): v for k, v in statuses.items()}})

    # --- Viewings ---

    def _handle_add_viewing(self, body: dict):
        try:
            prop_id = int(body["property_id"])
            viewing_date = body["viewing_date"]
            viewing_time = body.get("viewing_time", "")
            notes = body.get("notes", "")
        except (KeyError, ValueError):
            self._json_response(400, {"error": "property_id and viewing_date required"})
            return
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            vid = repo.add_viewing(prop_id, viewing_date, viewing_time, notes)
            self._json_response(200, {"action": "added", "id": vid})

    def _handle_update_viewing(self, viewing_id: int, body: dict):
        try:
            viewing_date = body["viewing_date"]
        except KeyError:
            self._json_response(400, {"error": "viewing_date required"})
            return
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            repo.update_viewing(
                viewing_id,
                viewing_date,
                body.get("viewing_time", ""),
                body.get("status", "scheduled"),
                body.get("notes", ""),
            )
            self._json_response(200, {"action": "updated", "id": viewing_id})

    def _handle_delete_viewing(self, viewing_id: int):
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            repo.delete_viewing(viewing_id)
            self._json_response(200, {"action": "deleted", "id": viewing_id})

    def _handle_all_viewings(self):
        with Database(self.db_path) as db:
            repo = PropertyRepository(db)
            self._json_response(200, {"viewings": repo.get_all_viewings()})

    # --- Enquiry autofill ---

    def _handle_enquiry(self, prop_db_id: int):
        """Launch Playwright to auto-fill the Rightmove contact form for a property."""
        import threading
        from ..config_loader import load_config

        # Look up the property to get portal_id and address
        try:
            with Database(self.db_path) as db:
                repo = PropertyRepository(db)
                prop = repo.get_property(prop_db_id)
        except Exception as exc:
            logger.error(f"Enquiry: DB lookup failed: {exc}")
            self._json_response(500, {"error": "DB lookup failed"})
            return

        if not prop:
            self._json_response(404, {"error": "Property not found"})
            return

        portal_id = prop.get("portal_id") or prop.get("rightmove_id", "")
        if not portal_id:
            self._json_response(400, {"error": "No portal_id for this property"})
            return

        cfg = load_config()
        user = cfg.get("user", {}) if isinstance(cfg, dict) else {}
        full_name = str(user.get("name", ""))
        first_name = full_name.split()[0] if full_name else ""
        last_name  = " ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else ""
        email      = str(user.get("email", ""))
        phone      = str(user.get("phone", ""))
        postcode   = str(user.get("postcode", ""))

        # Build the message
        from datetime import date, timedelta
        today = date.today()
        days_to_sat = (5 - today.weekday()) % 7 or 7
        sat = today + timedelta(days=days_to_sat)
        sun = sat + timedelta(days=1)
        sat_str = sat.strftime("%A %d %B").replace(" 0", " ")
        sun_str = sun.strftime("%A %d %B").replace(" 0", " ")

        address = prop.get("address") or prop.get("title", "the property")
        price   = prop.get("price", "")
        price_fmt = f"\u00a3{int(price):,}" if price else ""
        prop_url = prop.get("url", "")
        agent   = prop.get("agent_name", "Estate Agent")

        message = (
            f"Dear {agent},\n\n"
            f"I am writing to enquire about the property listed at {address}{' (' + price_fmt + ')' if price_fmt else ''}.\n\n"
            f"{prop_url}\n\n"
            f"I am a first-time buyer with a mortgage agreement in principle and a deposit ready. "
            f"I would love to arrange a viewing this weekend \u2014 I am available on {sat_str} or {sun_str} "
            f"and would be grateful if you could confirm a convenient time.\n\n"
            f"Could you please also let me know:\n"
            f"1. Whether there has been any interest or offers on the property\n"
            f"2. Any additional information about the property not covered in the listing\n\n"
            f"I look forward to hearing from you.\n\n"
            f"Kind regards\n{full_name}"
            + (f"\nTel: {phone}" if phone else "")
            + (f"\n{email}" if email else "")
        )

        def _fill():
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=False)
                    page = browser.new_page()
                    form_url = f"https://www.rightmove.co.uk/property-for-sale/contactBranch.html?propertyId={portal_id}"
                    page.goto(form_url, wait_until="networkidle")

                    if first_name:
                        page.fill("#firstName", first_name)
                    if last_name:
                        page.fill("#lastName", last_name)
                    if email:
                        page.fill("#email", email)
                    if phone:
                        # CSS escaping: phone.number -> phone\\.number
                        try:
                            page.fill("#phone\\.number", phone)
                        except Exception:
                            page.evaluate(f"el = document.querySelector('[name=\"phone.number\"]'); if(el) el.value = {phone!r}")
                    if postcode:
                        page.fill("#postcode", postcode)
                    if message:
                        page.fill("#comments", message)

                    # Check "I'd like to view this property"
                    cb = page.query_selector("#toViewProperty")
                    if cb and not cb.is_checked():
                        cb.check()

                    page.evaluate("window.focus()")
                    # Keep browser open until user closes it (max 5 min)
                    page.wait_for_event("close", timeout=300_000)
            except Exception as exc:
                logger.warning(f"Enquiry autofill failed: {exc}")

        threading.Thread(target=_fill, daemon=True).start()
        self._json_response(200, {"message": "Form opened \u2014 solve the CAPTCHA and click Send!"})

    def _handle_regenerate(self):
        """Re-run the report generator in-process and refresh the report file."""
        try:
            from ..config_loader import load_config
            from ..reporting.report_generator import ReportGenerator
            from datetime import date
            from pathlib import Path

            config = load_config()
            today = date.today().isoformat()
            output_path = str(Path(self.report_dir) / f"report_{today}.html")

            with Database(self.db_path) as db:
                repo = PropertyRepository(db)
                properties = repo.get_active_properties()
                enrichment_map = {}
                price_history_map = {}
                for prop in properties:
                    e = repo.get_enrichment(prop["id"])
                    if e:
                        enrichment_map[prop["id"]] = e
                    ph = repo.get_price_history(prop["id"])
                    if ph:
                        price_history_map[prop["id"]] = ph
                fav_ids = repo.get_favourite_ids()
                excl_ids = repo.get_excluded_ids()

            generator = ReportGenerator(config)
            generator.generate(
                properties, output_path, enrichment_map,
                favourite_ids=fav_ids, excluded_ids=excl_ids,
                price_history_map=price_history_map,
            )
            logger.info(f"Regenerated report: {output_path} ({len(properties)} properties)")
            self._json_response(200, {"action": "regenerated", "count": len(properties)})
        except Exception as exc:
            logger.error(f"Regenerate failed: {exc}")
            self._json_response(500, {"error": str(exc)})

    def _serve_latest_report(self):
        report_dir = Path(self.report_dir)
        reports = sorted(report_dir.glob("report_*.html"), reverse=True)
        if not reports:
            self._json_response(404, {"error": "No reports found"})
            return
        content = reports[0].read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        # Suppress default access logs for cleaner output
        if "/api/" in str(args[0]):
            logger.debug(format % args)


def start_server(port: int = 8765, report_dir: str = "output/reports", db_path: str = None):
    """Start the local report server."""
    if db_path is None:
        db_path = get_db_path()

    report_path = Path(report_dir)
    if not report_path.exists():
        report_path.mkdir(parents=True, exist_ok=True)

    handler = partial(
        ReportAPIHandler,
        report_dir=str(report_path.resolve()),
        db_path=db_path,
    )

    server = HTTPServer(("127.0.0.1", port), handler)
    print(f"Report server running at http://localhost:{port}")
    print(f"Serving reports from: {report_path.resolve()}")
    print("Press Ctrl+C to stop.")

    try:
        import webbrowser
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
