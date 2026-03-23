"""Accurately count cards per section in report HTML."""
import re
from pathlib import Path

html = Path("output/reports/report_2026-03-23.html").read_text(encoding="utf-8")

# Define section boundaries (order matters)
section_order = [
    "sec-shortlisted",
    "sec-favourites", 
    "sec-viewings",
    "sec-offers",
    "sec-qualifying",
    "sec-needs-verification",
    "sec-opportunities",
    "sec-near-misses",
    "sec-areas",
]

positions = {}
for sec_id in section_order:
    pos = html.find(f'id="{sec_id}"')
    if pos >= 0:
        positions[sec_id] = pos

sorted_sections = sorted(positions.items(), key=lambda x: x[1])

print("=== CARD COUNT PER SECTION ===\n")
for i, (sec_id, start) in enumerate(sorted_sections):
    end = sorted_sections[i + 1][1] if i + 1 < len(sorted_sections) else len(html)
    section_html = html[start:end]
    card_ids = re.findall(r'id="card-(\d+)"', section_html)
    print(f"{sec_id}: {len(card_ids)} cards → {card_ids}")

# Also check data-area attributes on favourite cards
print("\n=== FAVOURITE CARD DETAILS ===\n")
fav_start = positions.get("sec-favourites", 0)
fav_end_key = "sec-viewings"
fav_end = positions.get(fav_end_key, len(html))
fav_html = html[fav_start:fav_end]

# Find all cards and their data-area
cards = re.finditer(r'id="card-(\d+)"([^>]*)', fav_html)
for card in cards:
    card_id = card.group(1)
    attrs = card.group(2)
    area = re.search(r'data-area="([^"]*)"', attrs)
    hidden = re.search(r'style="[^"]*display:\s*none', attrs)
    area_val = area.group(1) if area else "NONE"
    hidden_val = "HIDDEN" if hidden else "visible"
    print(f"  #{card_id} area={area_val} {hidden_val}")

# Check if filter bar has JS that hides cards
print("\n=== AREA FILTER STATE ===\n")
# Look for the filter-bar and its active state
filter_match = re.search(r'id="filter-bar"(.*?)(?=</div>\s*</div>)', html, re.DOTALL)
if filter_match:
    btns = re.findall(r'data-area="([^"]*)"', filter_match.group(1))
    active = re.findall(r'class="[^"]*active[^"]*"[^>]*data-area="([^"]*)"', filter_match.group(1))
    print(f"  Filter buttons: {btns}")
    print(f"  Active filter: {active}")
else:
    print("  No filter bar found")

# Check for JS area filtering that could affect visibility
area_js = re.search(r'function\s+filterByArea|filterArea|areaFilter', html)
if area_js:
    # Get surrounding context
    start_pos = max(0, area_js.start() - 50)
    end_pos = min(len(html), area_js.end() + 500)
    print(f"\n  JS filter function found near position {area_js.start()}")
