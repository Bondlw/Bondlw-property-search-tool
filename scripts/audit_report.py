"""Audit report section counts to verify what's visible matches the numbers."""

import sys
import re
from pathlib import Path

# Read the generated report HTML
report_path = Path("output/reports/report_2026-03-23.html")
if not report_path.exists():
    print(f"Report not found: {report_path}")
    sys.exit(1)

html = report_path.read_text(encoding="utf-8")

print("=" * 70)
print("REPORT AUDIT — Section Count Verification")
print("=" * 70)

# 1. Hero/Summary stats
print("\n--- HERO SUMMARY STATS ---")
# Extract values from the summary stats section
summary_block = re.search(r'class="summary">(.*?)</div>\s*</div>\s*</div>\s*</div>\s*</div>\s*</div>\s*</div>', html, re.DOTALL)
stat_pairs = re.findall(r'class="value">(.*?)</div>\s*<div class="label">(.*?)</div>', html)
for value, label in stat_pairs:
    value = value.strip()
    label = label.strip()
    print(f"  {label}: {value}")

# 2. Navigation bar counts
print("\n--- NAV BAR COUNTS ---")
nav_counts = re.findall(r'<a href="#sec-[\w-]+"[^>]*>([\w\s]+)<span class="badge-count"[^>]*>(\d+)</span>', html)
for label, count in nav_counts:
    print(f"  {label.strip()}: {count}")

# 3. Section header counts (from <summary> tags)
print("\n--- SECTION HEADER COUNTS ---")
section_headers = re.findall(r'<summary>(.*?)</summary>', html)
for header in section_headers:
    # Extract count in parens
    match = re.search(r'([\w\s—]+).*?\((\d+)\)', header)
    if match:
        label = match.group(1).strip()
        count = match.group(2)
        print(f"  {label}: ({count})")

# 4. Actual card counts per section
print("\n--- ACTUAL CARDS RENDERED PER SECTION ---")
sections = {
    "sec-shortlisted": "Shortlisted",
    "sec-favourites": "Favourites",
    "sec-qualifying": "Qualifying",
    "sec-needs-verification": "Needs Verification",
    "sec-opportunities": "Opportunities",
    "sec-near-misses": "Near Misses",
}

for section_id, label in sections.items():
    # Find the section by its id
    pattern = rf'id="{section_id}">(.*?)(?=<details\s|$)'
    section_match = re.search(pattern, html, re.DOTALL)
    if section_match:
        section_html = section_match.group(1)
        # Count property cards (each card has class="card")
        card_count = len(re.findall(r'class="card\b', section_html))
        print(f"  {label}: {card_count} cards")
    else:
        print(f"  {label}: section not found")

# 5. List actual property IDs per section
print("\n--- PROPERTY IDs PER SECTION ---")
for section_id, label in sections.items():
    pattern = rf'id="{section_id}">(.*?)(?=<details\s|$)'
    section_match = re.search(pattern, html, re.DOTALL)
    if section_match:
        section_html = section_match.group(1)
        # Extract property IDs from data-id attributes
        prop_ids = re.findall(r'data-id="(\d+)"', section_html)
        if prop_ids:
            print(f"  {label}: {', '.join(prop_ids)}")
        else:
            # Try id="card-{id}" pattern
            card_ids = re.findall(r'id="card-(\d+)"', section_html)
            if card_ids:
                print(f"  {label}: {', '.join(card_ids)}")
            else:
                print(f"  {label}: no IDs found")
    else:
        print(f"  {label}: section not found")

# 6. Cross-check: do any property IDs appear in multiple sections?
print("\n--- DUPLICATE CHECK ---")
all_section_ids = {}
for section_id, label in sections.items():
    pattern = rf'id="{section_id}">(.*?)(?=<details\s|$)'
    section_match = re.search(pattern, html, re.DOTALL)
    if section_match:
        section_html = section_match.group(1)
        prop_ids = re.findall(r'data-id="(\d+)"', section_html)
        if not prop_ids:
            prop_ids = re.findall(r'id="card-(\d+)"', section_html)
        for pid in prop_ids:
            if pid in all_section_ids:
                all_section_ids[pid].append(label)
            else:
                all_section_ids[pid] = [label]

duplicates = {pid: secs for pid, secs in all_section_ids.items() if len(secs) > 1}
if duplicates:
    print("  ⚠ DUPLICATES FOUND:")
    for pid, secs in duplicates.items():
        print(f"    #{pid} appears in: {', '.join(secs)}")
else:
    print("  ✓ No duplicates — each property appears in exactly one section")

# 7. Verify counts match
print("\n--- CONSISTENCY CHECK ---")
# Compare hero count vs nav count vs section header count vs actual cards
print("  Checking if displayed counts match actual card counts...")

# Get section-level counts from headers
header_counts = {}
for header in section_headers:
    for section_id, label in sections.items():
        if label.lower().replace(" ", "") in header.lower().replace(" ", "").replace("—", ""):
            match = re.search(r'\((\d+)\)', header)
            if match:
                header_counts[label] = int(match.group(1))

for section_id, label in sections.items():
    pattern = rf'id="{section_id}">(.*?)(?=<details\s|$)'
    section_match = re.search(pattern, html, re.DOTALL)
    if section_match:
        section_html = section_match.group(1)
        card_count = len(re.findall(r'class="card\b', section_html))
        header_count = header_counts.get(label)
        if header_count is not None:
            if header_count == card_count:
                print(f"  ✓ {label}: header says ({header_count}), actual cards = {card_count}")
            else:
                print(f"  ✗ {label}: header says ({header_count}), but actual cards = {card_count} ← MISMATCH!")
        else:
            print(f"  ? {label}: no header count found, actual cards = {card_count}")
