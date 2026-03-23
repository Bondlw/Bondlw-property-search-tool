import re
html = open("output/reports/report_2026-03-23.html", encoding="utf-8").read()
stats = re.findall(r'class="value">(.*?)</div>\s*<div class="label">(.*?)</div>', html)
for val, label in stats:
    clean = re.sub(r'<[^>]+>', ' ', val).strip()
    print(f"  {label}: {clean}")
