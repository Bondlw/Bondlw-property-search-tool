"""Verify the generated report HTML has consistent counts."""
import re
from pathlib import Path

html = Path("output/reports/report_2026-03-23.html").read_text(encoding="utf-8")

print("=== GENERATED HTML COUNT VERIFICATION ===\n")

# Hero stat for qualifying
hero_q = re.search(r'stat green.*?class="value">(.*?)</div>', html, re.DOTALL)
if hero_q:
    raw = hero_q.group(1).strip()
    # Strip HTML tags to get readable text
    clean = re.sub(r'<[^>]+>', ' ', raw).strip()
    print(f"Hero Qualifying: {clean}")

# Hero stat for needs verifying
hero_nv = re.search(r'Needs Verifying.*?class="value">(.*?)</div>', html, re.DOTALL)
if not hero_nv:
    # Try from the stat block order
    stats = re.findall(r'class="value">(.*?)</div>\s*<div class="label">(.*?)</div>', html)
    for val, label in stats:
        clean_val = re.sub(r'<[^>]+>', ' ', val).strip()
        print(f"  Hero {label}: {clean_val}")

# Nav counts
nav = re.findall(r'<a href="#sec-[\w-]+"[^>]*>([\w\s]+)<span class="badge-count"[^>]*>(\d+)</span>', html)
print("\nNav bar:")
for label, count in nav:
    print(f"  {label.strip()}: {count}")

# Section header counts
headers = re.findall(r'<summary>(.*?)</summary>', html)
print("\nSection headers:")
for h in headers:
    m = re.search(r'([\w\s—\']+).*?\((\d+)\)', h)
    if m:
        print(f"  {m.group(1).strip()}: ({m.group(2)})")

# Count actual cards per section (count card- IDs)
print("\nActual card IDs per section:")
# Split by section boundaries
section_pattern = r'id="(sec-[\w-]+)"'
section_starts = [(m.start(), m.group(1)) for m in re.finditer(section_pattern, html)]
for i, (start, sec_id) in enumerate(section_starts):
    end = section_starts[i+1][0] if i+1 < len(section_starts) else len(html)
    chunk = html[start:end]
    card_ids = re.findall(r'id="card-(\d+)"', chunk)
    if card_ids:
        print(f"  {sec_id}: {len(card_ids)} cards → [{', '.join(card_ids)}]")
    else:
        count = chunk.count('class="card ')
        if count > 0:
            print(f"  {sec_id}: {count} cards (no IDs found)")
        else:
            print(f"  {sec_id}: 0 cards")
