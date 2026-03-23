"""Count exact favourites in the latest generated report HTML."""
import re
from pathlib import Path

# Find the latest report
report_dir = Path("output/reports")
reports = sorted(report_dir.glob("report_*.html"), reverse=True)
if not reports:
    print("No reports found!")
    exit(1)

latest = reports[0]
print(f"Latest report: {latest.name}")
html = latest.read_text(encoding="utf-8")

# Find the favourites section
fav_match = re.search(r'id="sec-favourites">(.*?)(?=<details\s)', html, re.DOTALL)
if not fav_match:
    print("Favourites section not found!")
    exit(1)

fav_html = fav_match.group(1)

# Count cards
card_ids = re.findall(r'id="card-(\d+)"', fav_html)
print(f"Favourites section card count: {len(card_ids)}")
print(f"Card IDs: {card_ids}")

# Check header count
header_match = re.search(r'fav-count[^>]*>\((\d+)\)', fav_html)
if header_match:
    print(f"Header shows: ({header_match.group(1)})")

# Check nav count
nav_fav = re.search(r'nav-fav-count[^>]*>(\d+)<', html)
if nav_fav:
    print(f"Nav bar shows: {nav_fav.group(1)}")

# Check for any JS that filters/hides cards
# Look for area filter or other filter mechanisms
filter_bar = re.search(r'class="filter-bar"(.*?)(?=</nav>|</div>\s*<details)', html, re.DOTALL)
if filter_bar:
    area_buttons = re.findall(r'data-area="([^"]+)"', filter_bar.group(1))
    print(f"\nFilter bar areas: {area_buttons}")

# Check if there's an area filter that defaults to a specific area
area_filter_default = re.search(r'activeArea\s*=\s*["\']([^"\']*)["\']', html)
if area_filter_default:
    print(f"Default area filter: {area_filter_default.group(1)}")

# Check each favourite's search area
for card_id in card_ids:
    # Find the card and its area data attribute
    card_match = re.search(rf'id="card-{card_id}"[^>]*data-area="([^"]*)"', html)
    if card_match:
        print(f"  Card #{card_id} area: {card_match.group(1)}")
    else:
        # Try without data-area
        card_match2 = re.search(rf'id="card-{card_id}"[^>]*>', html)
        if card_match2:
            attrs = card_match2.group(0)
            area = re.search(r'data-area="([^"]*)"', attrs)
            print(f"  Card #{card_id} area: {area.group(1) if area else 'NO DATA-AREA ATTR'}")
