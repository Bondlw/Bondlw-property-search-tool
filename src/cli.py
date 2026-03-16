"""CLI interface for the UK Property Search Tool."""

import logging
import sys
import time
from datetime import date
from pathlib import Path

import click

from .config_loader import load_config, get_all_areas
from .enrichment.enrichment_service import EnrichmentService
from .notifications.notifier import Notifier
from .reporting.report_generator import ReportGenerator
from .scrapers.http_client import HttpClient
from .scrapers.rightmove_scraper import RightmoveScraper
from .storage.database import Database
from .storage.repository import PropertyRepository
from .utils.deduplication import normalise_url

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def get_db_path() -> str:
    """Get the database path relative to the project root."""
    return str(Path(__file__).parent.parent / "data" / "property_search.db")


@click.group()
@click.pass_context
def cli(ctx):
    """UK Property Search Tool — find your next home."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config()


@cli.command()
@click.pass_context
def init(ctx):
    """Initialise the database."""
    db_path = get_db_path()
    with Database(db_path) as db:
        db.init_schema()
    click.echo(f"Database initialised at {db_path}")


@cli.command()
@click.option("--portal", default="rightmove", help="Portal to search (rightmove)")
@click.option("--area", default="all", help="Area name or 'all'")
@click.option("--skip-detail", is_flag=True, help="Skip fetching individual listing details")
@click.pass_context
def run(ctx, portal, area, skip_detail):
    """Full pipeline: search -> fetch details -> generate report."""
    config = ctx.obj["config"]
    db_path = get_db_path()
    today = date.today().isoformat()

    with Database(db_path) as db:
        repo = PropertyRepository(db)
        http_client = HttpClient(config)

        # Step 1: Search
        click.echo("=== Step 1: Searching portals ===")
        scrapers = {}
        if portal in ("rightmove", "all"):
            scrapers["rightmove"] = RightmoveScraper(http_client)

        areas_list = get_all_areas(config)
        if area != "all":
            areas_list = [a for a in areas_list if a["name"].lower() == area.lower()]

        start_time = time.time()
        total_found = 0
        total_new = 0
        total_updated = 0
        errors = []

        for area_config in areas_list:
            area_name = area_config["name"]
            click.echo(f"\nSearching {area_name}...")

            for portal_name, scraper in scrapers.items():
                try:
                    listings = scraper.search(area_config, config.get("budget", {}))
                    total_found += len(listings)

                    for listing in listings:
                        url_norm = normalise_url(listing.url)
                        existing_id = repo.property_exists(listing.portal, listing.portal_id)

                        if existing_id:
                            price_changed = repo.update_property(existing_id, listing)
                            if price_changed:
                                total_updated += 1
                                click.echo(f"  Updated: {listing.address} (price changed)")
                        else:
                            repo.insert_property(listing, url_norm)
                            total_new += 1

                except Exception as e:
                    error_msg = f"Error scraping {portal_name}/{area_name}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

        click.echo(f"\nSearch: Found {total_found} | New: {total_new} | Updated: {total_updated}")

        # Step 2: Fetch details
        if not skip_detail:
            click.echo("\n=== Step 2: Fetching listing details ===")
            needs_detail = repo.get_properties_needing_details()
            if needs_detail:
                click.echo(f"Fetching details for {len(needs_detail)} properties...")
                scraper = scrapers.get("rightmove") or RightmoveScraper(http_client)
                detail_ok = 0
                detail_fail = 0

                for i, prop in enumerate(needs_detail):
                    try:
                        listing = scraper.get_listing_detail(prop["url"])
                        if listing:
                            repo.update_property_details(prop["id"], listing)
                            if listing.nearest_stations:
                                best = listing.nearest_stations[0]
                                repo.upsert_enrichment({
                                    "property_id": prop["id"],
                                    "nearest_station_name": best["name"],
                                    "nearest_station_distance_m": best["distance_m"],
                                    "nearest_station_walk_min": best["walk_min"],
                                })
                            detail_ok += 1
                        else:
                            detail_fail += 1
                    except Exception as e:
                        detail_fail += 1
                        logger.error(f"Detail fetch error: {e}")

                    if (i + 1) % 10 == 0:
                        click.echo(f"  Progress: {i+1}/{len(needs_detail)}")

                click.echo(f"Details: {detail_ok} fetched | {detail_fail} failed")
            else:
                click.echo("All properties already have details.")

        # Step 3: Enrich (crime + supermarkets + commute)
        if not skip_detail:
            click.echo("\n=== Step 3: Enriching properties ===")
            needs_enrichment = repo.get_properties_needing_enrichment()
            if needs_enrichment:
                enrichment_svc = EnrichmentService(config)
                click.echo(f"Enriching {len(needs_enrichment)} properties...")
                for i, prop in enumerate(needs_enrichment):
                    try:
                        existing = repo.get_enrichment(prop["id"])
                        enrichment_data = enrichment_svc.enrich(prop, existing)
                        repo.upsert_enrichment(enrichment_data)
                    except Exception as e:
                        logger.error(f"Enrichment error for {prop.get('address')}: {e}")
                    if (i + 1) % 5 == 0:
                        click.echo(f"  Progress: {i+1}/{len(needs_enrichment)}")
                click.echo(f"Enrichment done for {len(needs_enrichment)} properties.")
            else:
                click.echo("All properties already enriched.")

        # Step 4: Generate report
        click.echo("\n=== Step 4: Generating report ===")
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

        output_dir = Path(__file__).parent.parent / "output" / "reports"
        output_path = str(output_dir / f"report_{today}.html")

        generator = ReportGenerator(config)
        fav_ids = repo.get_favourite_ids()
        excl_ids = repo.get_excluded_ids()
        path = generator.generate(properties, output_path, enrichment_map,
                                  favourite_ids=fav_ids, excluded_ids=excl_ids,
                                  price_history_map=price_history_map)

        duration = time.time() - start_time

        # Compute summary stats for notifications
        qualifying_list = generator.last_qualifying or []
        new_today_list = generator.last_new_today or []
        near_miss_list = generator.last_near_misses or []

        repo.log_run(
            run_type="full_pipeline",
            properties_found=total_found,
            new_properties=total_new,
            updated_properties=total_updated,
            qualifying_count=len(qualifying_list),
            duration_seconds=duration,
            errors=errors,
        )

        click.echo(f"\n=== Pipeline Complete ({duration:.1f}s) ===")
        click.echo(f"Qualifying: {len(qualifying_list)} | New: {len(new_today_list)} | Near miss: {len(near_miss_list)}")
        click.echo(f"Report: {path}")

        # Notifications
        notifier = Notifier(config)
        notifier.notify(
            qualifying_count=len(qualifying_list),
            new_count=len(new_today_list),
            near_miss_count=len(near_miss_list),
            report_path=path,
            top_properties=qualifying_list[:5],
        )
        click.echo("Notifications sent.")

        import webbrowser
        try:
            webbrowser.open(f"file:///{Path(path).resolve()}")
        except Exception:
            pass


@cli.command()
@click.option("--portal", default="rightmove", help="Portal to search (rightmove)")
@click.option("--area", default="all", help="Area name or 'all'")
@click.pass_context
def search(ctx, portal, area):
    """Scrape property listings from portals."""
    config = ctx.obj["config"]
    db_path = get_db_path()

    areas = get_all_areas(config)
    if area != "all":
        areas = [a for a in areas if a["name"].lower() == area.lower()]
        if not areas:
            click.echo(f"Area '{area}' not found in config.")
            return

    with Database(db_path) as db:
        repo = PropertyRepository(db)
        http_client = HttpClient(config)

        scrapers = {}
        if portal in ("rightmove", "all"):
            scrapers["rightmove"] = RightmoveScraper(http_client)

        start_time = time.time()
        total_found = 0
        total_new = 0
        total_updated = 0
        errors = []

        for area_config in areas:
            area_name = area_config["name"]
            click.echo(f"\nSearching {area_name}...")

            for portal_name, scraper in scrapers.items():
                try:
                    listings = scraper.search(area_config, config.get("budget", {}))
                    total_found += len(listings)

                    for listing in listings:
                        url_norm = normalise_url(listing.url)

                        # Check if exists
                        existing_id = repo.property_exists(
                            listing.portal, listing.portal_id
                        )

                        if existing_id:
                            price_changed = repo.update_property(
                                existing_id, listing
                            )
                            if price_changed:
                                total_updated += 1
                                click.echo(
                                    f"  Updated: {listing.address} "
                                    f"(price changed to £{listing.price:,})"
                                )
                        else:
                            prop_id = repo.insert_property(listing, url_norm)
                            total_new += 1
                            click.echo(
                                f"  New: {listing.address} - "
                                f"£{listing.price:,} ({listing.property_type})"
                            )

                except Exception as e:
                    error_msg = f"Error scraping {portal_name}/{area_name}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

        duration = time.time() - start_time

        # Log the run
        repo.log_run(
            run_type="search",
            properties_found=total_found,
            new_properties=total_new,
            updated_properties=total_updated,
            duration_seconds=duration,
            errors=errors,
        )

        click.echo(f"\n--- Search Complete ---")
        click.echo(f"Found: {total_found} | New: {total_new} | Updated: {total_updated}")
        click.echo(f"Duration: {duration:.1f}s")
        if errors:
            click.echo(f"Errors: {len(errors)}")


@cli.command()
@click.option("--limit", default=0, help="Max properties to fetch details for (0=all)")
@click.pass_context
def detail(ctx, limit):
    """Fetch full listing details for properties missing them."""
    config = ctx.obj["config"]
    db_path = get_db_path()

    with Database(db_path) as db:
        repo = PropertyRepository(db)
        http_client = HttpClient(config)
        scraper = RightmoveScraper(http_client)

        props = repo.get_properties_needing_details()
        if limit > 0:
            props = props[:limit]

        if not props:
            click.echo("All properties already have details.")
            return

        click.echo(f"Fetching details for {len(props)} properties...")

        start_time = time.time()
        success = 0
        failed = 0

        for i, prop in enumerate(props):
            prop_id = prop["id"]
            url = prop["url"]

            try:
                listing = scraper.get_listing_detail(url)
                if listing:
                    repo.update_property_details(prop_id, listing)

                    # Store nearest station in enrichment_data
                    if listing.nearest_stations:
                        best = listing.nearest_stations[0]
                        repo.upsert_enrichment({
                            "property_id": prop_id,
                            "nearest_station_name": best["name"],
                            "nearest_station_distance_m": best["distance_m"],
                            "nearest_station_walk_min": best["walk_min"],
                        })

                    success += 1
                    tenure_str = listing.tenure or "?"
                    lease_str = f" ({listing.lease_years}yr)" if listing.lease_years else ""
                    station_str = f" | {listing.nearest_stations[0]['name']} {listing.nearest_stations[0]['walk_min']}min" if listing.nearest_stations else ""
                    click.echo(
                        f"  [{i+1}/{len(props)}] {listing.address} — "
                        f"{tenure_str}{lease_str}{station_str}"
                    )
                else:
                    failed += 1
                    click.echo(f"  [{i+1}/{len(props)}] FAILED: {url}")
            except Exception as e:
                failed += 1
                logger.error(f"Error fetching detail for {url}: {e}")

        duration = time.time() - start_time
        click.echo(
            f"\n--- Detail Fetch Complete ---\n"
            f"Success: {success} | Failed: {failed} | Duration: {duration:.1f}s"
        )


@cli.command()
@click.option("--limit", default=0, help="Max properties to enrich (0=all needing it)")
@click.pass_context
def enrich(ctx, limit):
    """Fetch crime, walkability, and commute data for properties."""
    config = ctx.obj["config"]
    db_path = get_db_path()

    with Database(db_path) as db:
        repo = PropertyRepository(db)
        service = EnrichmentService(config)

        props = repo.get_properties_needing_enrichment()
        if limit > 0:
            props = props[:limit]

        if not props:
            click.echo("All properties already enriched.")
            return

        click.echo(f"Enriching {len(props)} properties (crime + walkability + commute)...")
        start_time = time.time()
        success = 0
        failed = 0

        for i, prop in enumerate(props):
            try:
                existing = repo.get_enrichment(prop["id"])
                enrichment = service.enrich(prop, existing)
                repo.upsert_enrichment(enrichment)
                success += 1

                parts = []
                if enrichment.get("crime_summary"):
                    crime = enrichment.get("crime_summary")
                    if isinstance(crime, str):
                        import json as _json
                        crime = _json.loads(crime)
                    parts.append(f"crime={crime.get('total', '?')}/mo")
                if enrichment.get("nearest_lidl_walk_min"):
                    parts.append(f"Lidl={enrichment['nearest_lidl_walk_min']}min")
                if enrichment.get("nearest_aldi_walk_min"):
                    parts.append(f"Aldi={enrichment['nearest_aldi_walk_min']}min")
                if enrichment.get("commute_to_maidstone_min"):
                    parts.append(f"Maidstone={enrichment['commute_to_maidstone_min']}min")

                detail = " | ".join(parts) if parts else "no data"
                click.echo(f"  [{i+1}/{len(props)}] {prop['address'][:40]} — {detail}")

            except Exception as e:
                failed += 1
                logger.error(f"Enrichment failed for {prop.get('address')}: {e}")

        duration = time.time() - start_time
        click.echo(f"\n--- Enrichment Complete ---\nSuccess: {success} | Failed: {failed} | {duration:.1f}s")


@cli.command("backfill-supermarkets")
@click.option("--limit", default=0, help="Max properties to backfill (0=all)")
@click.pass_context
def backfill_supermarkets(ctx, limit):
    """Re-fetch supermarket data for properties missing it."""
    config = ctx.obj["config"]
    db_path = get_db_path()

    with Database(db_path) as db:
        repo = PropertyRepository(db)

        rows = db.conn.execute(
            """SELECT p.id, p.url, p.address, p.postcode, p.latitude, p.longitude
               FROM properties p
               INNER JOIN enrichment_data e ON p.id = e.property_id
               WHERE p.is_active = 1
               AND p.latitude IS NOT NULL
               AND e.nearest_supermarket_name IS NULL
               ORDER BY p.first_seen_date DESC"""
        ).fetchall()
        props = [dict(r) for r in rows]

        if limit > 0:
            props = props[:limit]

        if not props:
            click.echo("All enriched properties already have supermarket data.")
            return

        click.echo(f"Backfilling supermarket data for {len(props)} properties...")
        service = EnrichmentService(config)
        success = 0
        failed = 0

        for i, prop in enumerate(props):
            try:
                lat, lng = prop["latitude"], prop["longitude"]
                supers = service.fetch_supermarkets(lat, lng)
                if supers.get("nearest_supermarket_name"):
                    update = {"property_id": prop["id"]}
                    update.update(supers)
                    repo.upsert_enrichment(update)
                    success += 1
                    click.echo(
                        f"  [{i+1}/{len(props)}] {prop['address'][:45]} — "
                        f"{supers['nearest_supermarket_name']} {supers['nearest_supermarket_walk_min']}min walk"
                    )
                else:
                    failed += 1
                    click.echo(f"  [{i+1}/{len(props)}] {prop['address'][:45]} — no supermarkets found")
            except Exception as e:
                failed += 1
                logger.error(f"Supermarket backfill error for {prop['address']}: {e}")

            if (i + 1) % 20 == 0:
                click.echo(f"  Progress: {i+1}/{len(props)} ({success} ok, {failed} failed)")

        click.echo(f"\n--- Supermarket Backfill Complete ---")
        click.echo(f"Success: {success} | Failed: {failed}")


@cli.command("backfill-stations")
@click.option("--limit", default=0, help="Max properties to backfill (0=all)")
@click.pass_context
def backfill_stations(ctx, limit):
    """Re-fetch station data for properties that have enrichment but no station info."""
    config = ctx.obj["config"]
    db_path = get_db_path()

    with Database(db_path) as db:
        repo = PropertyRepository(db)
        http_client = HttpClient(config)
        scraper = RightmoveScraper(http_client)

        # Find properties with enrichment but no station data
        rows = db.conn.execute(
            """SELECT p.id, p.url, p.address
               FROM properties p
               INNER JOIN enrichment_data e ON p.id = e.property_id
               WHERE p.is_active = 1
               AND e.nearest_station_name IS NULL
               ORDER BY p.first_seen_date DESC"""
        ).fetchall()
        props = [dict(r) for r in rows]

        if limit > 0:
            props = props[:limit]

        if not props:
            click.echo("All enriched properties already have station data.")
            return

        click.echo(f"Backfilling station data for {len(props)} properties...")
        success = 0
        failed = 0

        for i, prop in enumerate(props):
            try:
                listing = scraper.get_listing_detail(prop["url"])
                if listing and listing.nearest_stations:
                    best = listing.nearest_stations[0]
                    repo.upsert_enrichment({
                        "property_id": prop["id"],
                        "nearest_station_name": best["name"],
                        "nearest_station_distance_m": best["distance_m"],
                        "nearest_station_walk_min": best["walk_min"],
                    })
                    success += 1
                    click.echo(
                        f"  [{i+1}/{len(props)}] {prop['address'][:45]} — "
                        f"{best['name']} {best['walk_min']}min walk"
                    )
                else:
                    failed += 1
                    click.echo(f"  [{i+1}/{len(props)}] {prop['address'][:45]} — no stations found")
            except Exception as e:
                failed += 1
                logger.error(f"Station backfill error for {prop['address']}: {e}")

            if (i + 1) % 20 == 0:
                click.echo(f"  Progress: {i+1}/{len(props)} ({success} ok, {failed} failed)")

        click.echo(f"\n--- Station Backfill Complete ---")
        click.echo(f"Success: {success} | Failed: {failed}")


@cli.command()
@click.pass_context
def report(ctx):
    """Generate HTML report from current data."""
    config = ctx.obj["config"]
    db_path = get_db_path()
    today = date.today().isoformat()
    output_dir = Path(__file__).parent.parent / "output" / "reports"
    output_path = str(output_dir / f"report_{today}.html")

    with Database(db_path) as db:
        repo = PropertyRepository(db)
        properties = repo.get_active_properties()

        if not properties:
            click.echo("No active properties in database.")
            return

        click.echo(f"Generating report for {len(properties)} properties...")

        # Load enrichment and price history data
        enrichment_map = {}
        price_history_map = {}
        for prop in properties:
            e = repo.get_enrichment(prop["id"])
            if e:
                enrichment_map[prop["id"]] = e
            ph = repo.get_price_history(prop["id"])
            if ph:
                price_history_map[prop["id"]] = ph

        generator = ReportGenerator(config)
        fav_ids = repo.get_favourite_ids()
        excl_ids = repo.get_excluded_ids()
        path = generator.generate(properties, output_path, enrichment_map,
                                  favourite_ids=fav_ids, excluded_ids=excl_ids,
                                  price_history_map=price_history_map)

        click.echo(f"Report saved: {path}")

        # Try to open in browser
        import webbrowser
        try:
            webbrowser.open(f"file:///{Path(path).resolve()}")
            click.echo("Opened in browser.")
        except Exception:
            pass


@cli.command()
@click.option("--port", default=8765, help="Port to serve on")
@click.pass_context
def serve(ctx, port):
    """Start local server for interactive report (favourite/exclude buttons)."""
    from .server.report_server import start_server

    db_path = get_db_path()
    report_dir = str(Path(__file__).parent.parent / "output" / "reports")
    click.echo(f"Starting report server on port {port}...")
    start_server(port=port, report_dir=report_dir, db_path=db_path)


@cli.command()
@click.pass_context
def status(ctx):
    """Show database statistics."""
    db_path = get_db_path()

    with Database(db_path) as db:
        repo = PropertyRepository(db)
        stats = repo.get_stats()

        click.echo(f"\n=== Property Search Database ===")
        click.echo(f"Total properties:  {stats['total']}")
        click.echo(f"Active:            {stats['active']}")
        click.echo(f"New today:         {stats['new_today']}")
        click.echo(f"Price reduced:     {stats['reduced']}")
        click.echo(f"Excluded:          {stats['excluded']}")

        # Per-area breakdown
        rows = db.conn.execute(
            """SELECT
                SUBSTR(postcode, 1, CASE
                    WHEN LENGTH(postcode) >= 5 THEN LENGTH(postcode) - 3
                    ELSE LENGTH(postcode)
                END) as area_code,
                COUNT(*) as count,
                AVG(price) as avg_price,
                MIN(price) as min_price,
                MAX(price) as max_price
               FROM properties
               WHERE is_active = 1 AND postcode IS NOT NULL AND postcode != ''
               GROUP BY area_code
               ORDER BY count DESC"""
        ).fetchall()

        if rows:
            click.echo(f"\n--- By Postcode Area ---")
            click.echo(f"{'Area':<8} {'Count':<7} {'Avg £':<10} {'Min £':<10} {'Max £':<10}")
            for row in rows:
                r = dict(row)
                click.echo(
                    f"{r['area_code']:<8} {r['count']:<7} "
                    f"£{r['avg_price']:>8,.0f} £{r['min_price']:>8,} £{r['max_price']:>8,}"
                )

        # Recent runs
        runs = db.conn.execute(
            "SELECT * FROM run_log ORDER BY created_at DESC LIMIT 5"
        ).fetchall()

        if runs:
            click.echo(f"\n--- Recent Runs ---")
            for run in runs:
                r = dict(run)
                click.echo(
                    f"{r['run_date'][:19]} | {r['run_type']:<12} | "
                    f"Found: {r['properties_found'] or 0} | "
                    f"New: {r['new_properties'] or 0} | "
                    f"Updated: {r['updated_properties'] or 0} | "
                    f"{r['duration_seconds']:.1f}s"
                )


@cli.command()
@click.pass_context
def areas(ctx):
    """List configured search areas."""
    config = ctx.obj["config"]
    all_areas = get_all_areas(config)

    click.echo(f"\n=== Search Areas ({len(all_areas)} configured) ===")
    for area in all_areas:
        rm_id = area.get("rightmove_id", "")
        status = "ready" if rm_id else "needs ID"
        click.echo(
            f"  [{area['area_type']:<9}] {area['name']:<20} "
            f"Rightmove ID: {rm_id or 'NOT SET':<20} ({status})"
        )


@cli.group()
def exclude():
    """Manage property exclusions."""


@exclude.command("add")
@click.argument("property_id", type=int)
@click.argument("reason")
def exclude_add(property_id, reason):
    """Exclude a property with a reason."""
    db_path = get_db_path()
    with Database(db_path) as db:
        repo = PropertyRepository(db)
        prop = repo.get_property(property_id)
        if not prop:
            click.echo(f"Property ID {property_id} not found.")
            return
        repo.add_exclusion(property_id, reason)
        click.echo(
            f"Excluded: {prop['address']} (£{prop['price']:,}) — {reason}"
        )


@exclude.command("remove")
@click.argument("property_id", type=int)
def exclude_remove(property_id):
    """Remove an exclusion."""
    db_path = get_db_path()
    with Database(db_path) as db:
        repo = PropertyRepository(db)
        repo.remove_exclusion(property_id)
        click.echo(f"Exclusion removed for property {property_id}")


@exclude.command("list")
def exclude_list():
    """List all excluded properties."""
    db_path = get_db_path()
    with Database(db_path) as db:
        repo = PropertyRepository(db)
        exclusions = repo.get_exclusions()

        if not exclusions:
            click.echo("No exclusions.")
            return

        click.echo(f"\n=== Excluded Properties ({len(exclusions)}) ===")
        for e in exclusions:
            click.echo(
                f"  ID {e['property_id']}: {e['address']} — "
                f"£{e['price']:,} — {e['reason']} "
                f"(excluded {e['excluded_at'][:10]})"
            )


# Register exclude subgroup
cli.add_command(exclude)


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
