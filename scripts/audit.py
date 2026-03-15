import re

html = open('output/reports/report_2026-03-14.html', encoding='utf-8').read()
issues = []

# 1. Old variable references surviving in output
for ref in ['sec-stretch', 'sec-negotiation']:
    if ref in html:
        issues.append('OLD REF still in output: ' + ref)

# 2. Jinja tags not rendered (would mean template error)
jinja_leftovers = re.findall(r'\{\{[^}]{1,80}\}\}', html)
if jinja_leftovers:
    issues.append('Unfilled Jinja tags (%d): %s' % (len(jinja_leftovers), str(jinja_leftovers[:3])))

# 3. Rendered None values
none_count = len(re.findall(r'>None<|>None </|" None"', html))
if none_count:
    issues.append('Rendered None values: %d occurrences' % none_count)

# 4. Duplicate card IDs
card_ids = re.findall(r'id="card-([0-9]+)"', html)
dupes = [x for x in set(card_ids) if card_ids.count(x) > 1]
if dupes:
    issues.append('Duplicate card IDs: %s' % str(dupes[:5]))

# 5. Summary stat label
if '<div class="label">Stretch</div>' in html:
    issues.append('Summary stat still says "Stretch" — should be "Opportunities"')

# 6. Near miss section description accuracy
if 'do not</strong> meet all criteria' in html:
    issues.append('Near miss description says "do not meet criteria" — but all now have qualifying offers')

# 7. Old negotiation description
if 'currently above GREEN but <strong>would qualify' in html:
    issues.append('Old negotiation section description still present')

# 8. Today's Actions references to old section name
if 'negotiation target' in html.lower() and 'sec-negotiation' in html:
    issues.append("Today's Actions still references 'negotiation targets' with old section link")

# 9. Broken supermarket pill (misplaced endif)
if 'min{% endif' in html:
    issues.append('Broken supermarket pill template (misplaced endif)')

# 10. Nav badge counts — check they match section heading counts
nav_opps = re.search(r'sec-opportunities.*?badge-count.*?(\d+)', html, re.DOTALL)
section_opps = re.search(r'id="sec-opportunities".*?Opportunities.*?\((\d+)\)', html, re.DOTALL)
if nav_opps and section_opps and nav_opps.group(1) != section_opps.group(1):
    issues.append('Opportunities nav badge (%s) != section count (%s)' % (nav_opps.group(1), section_opps.group(1)))

# 11. Check cost-bar classes in output (no raw 'None' class)
bad_cost_bars = re.findall(r'class="cost-bar None"', html)
if bad_cost_bars:
    issues.append('cost-bar with None class: %d cards' % len(bad_cost_bars))

# 12. Check section descriptions match new logic
qualifying_desc = re.search(r'sec-qualifying.*?<div style[^>]*>(.*?)</div>', html, re.DOTALL)
if qualifying_desc and 'GREEN' not in qualifying_desc.group(1):
    issues.append('Qualifying section description missing GREEN target mention')

print('=== ISSUES ===')
if issues:
    for i in issues:
        print('  [!] ' + i)
else:
    print('  None found')

print('\n=== COUNTS ===')
for label, pattern in [
    ('Qualifying', r'Qualifying Properties[^(]*\(([0-9]+)\)'),
    ('Opportunities', r'Opportunities[^(]*\(([0-9]+)\)'),
    ('Near Misses', r'Near Misses[^(]*\(([0-9]+)\)'),
    ('Favourites', r'<span class="count" id="fav-count">\(([0-9]+)\)'),
]:
    m = re.search(pattern, html)
    print('  %s: %s' % (label, m.group(1) if m else '?'))

print('\n=== SECTION DESCRIPTIONS ===')
for sec_id, sec_name in [('sec-qualifying', 'Qualifying'), ('sec-opportunities', 'Opportunities'), ('sec-near-misses', 'Near Misses')]:
    m = re.search(r'id="%s".*?<div style[^>]*color[^>]*>(.*?)</div>' % sec_id, html, re.DOTALL)
    if m:
        print('  [%s] %s' % (sec_name, re.sub(r'<[^>]+>', '', m.group(1)).strip()[:120]))

print('\n=== NAV BAR LINKS ===')
nav_links = re.findall(r'<a href="(#sec-[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
for href, text in nav_links:
    print('  %s -> %s' % (href, re.sub(r'<[^>]+>', '', text).strip()))
