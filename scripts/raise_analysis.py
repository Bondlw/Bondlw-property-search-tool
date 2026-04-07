import math

# === DISTANCE CALCULATION ===
lat1, lon1 = 51.146129, 0.276082  # Queripel Close
lat2, lon2 = 51.2722, 0.5218      # County Gate, Maidstone

R = 3959  # Earth radius in miles
dlat = math.radians(lat2 - lat1)
dlon = math.radians(lon2 - lon1)
a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
c = 2 * math.asin(math.sqrt(a))
distance_miles = R * c

threshold = 20
print('=== DISTANCE TO OFFICE ===')
print(f'  Queripel Close -> County Gate, Maidstone')
print(f'  Straight line: {distance_miles:.1f} miles')
print(f'  Remote threshold: {threshold} miles')
under_over = 'UNDER' if distance_miles < threshold else 'OVER'
print(f'  Gap: {threshold - distance_miles:+.1f} miles ({under_over} threshold)')
driving_est = distance_miles * 1.3
under_over_drive = 'UNDER' if driving_est < threshold else 'OVER'
print(f'  Est. driving distance: ~{driving_est:.0f} miles (1.3x crow-flies factor)')
print(f'  Driving vs threshold: {threshold - driving_est:+.1f} miles ({under_over_drive} threshold)')
print()

# === RAISE CALCULATION ===
rate = 0.045 / 12
term = 360
factor = (rate * (1+rate)**term) / ((1+rate)**term - 1)

bills = 198
council_tax = 95
service_charge = 1835 / 12
ground_rent = 137 / 12
fixed = bills + council_tax + service_charge + ground_rent

offer = 170000
deposit = 37500
loan = offer - deposit
mortgage = loan * factor
housing = mortgage + fixed

def net_from_gross(gross):
    pa = 12570
    taxable = max(0, gross - pa)
    basic = min(taxable, 50270 - pa)
    higher = max(0, taxable - (50270 - pa))
    tax = basic * 0.20 + higher * 0.40
    ni_earn = max(0, gross - pa)
    ni_basic = min(ni_earn, 50270 - pa)
    ni_higher = max(0, ni_earn - (50270 - pa))
    ni = ni_basic * 0.08 + ni_higher * 0.02
    return gross - tax - ni

current_gross = 42256
current_net_annual = net_from_gross(current_gross)
current_net_monthly = current_net_annual / 12
current_pct = (housing / current_net_monthly) * 100

print(f'=== RAISE ANALYSIS (Queripel at 170k) ===')
print(f'  Current gross: {current_gross:,}/yr')
print(f'  Current net: {current_net_monthly:,.0f}/mo')
print(f'  Housing cost: {housing:,.0f}/mo')
print(f'  Housing % now: {current_pct:.0f}%')
print()

targets = [
    (40, 'Less stretched (40%)'),
    (38, 'Reasonable (38%)'),
    (35, 'Tight but ok (35%)'),
    (33, 'Manageable (33%)'),
    (30, 'Comfortable (30%)'),
]

print(f'  Target               | Gross needed |    Raise |  Raise% |  Net/mo | Leftover')
print(f'  ---------------------+--------------+----------+---------+---------+---------')

for pct, label in targets:
    net_needed_monthly = housing / (pct / 100)
    net_needed_annual = net_needed_monthly * 12
    lo, hi = net_needed_annual, net_needed_annual * 2
    for _ in range(50):
        mid = (lo + hi) / 2
        if net_from_gross(mid) < net_needed_annual:
            lo = mid
        else:
            hi = mid
    gross_needed = (lo + hi) / 2
    raise_amount = gross_needed - current_gross
    raise_pct = (raise_amount / current_gross) * 100
    leftover = net_needed_monthly - housing
    print(f'  {label:20s} | {gross_needed:>11,.0f} | {raise_amount:>7,.0f} | {raise_pct:>6.1f}% | {net_needed_monthly:>7,.0f} | {leftover:>7,.0f}')

print()
print('=== REALISTIC RAISE SCENARIOS ===')
for raise_pct_try in [3, 5, 7, 10, 15, 20]:
    new_gross = current_gross * (1 + raise_pct_try/100)
    new_net = net_from_gross(new_gross) / 12
    new_pct = (housing / new_net) * 100
    extra_net = new_net - current_net_monthly
    leftover = new_net - housing
    print(f'  {raise_pct_try:>2}% raise: {current_gross:,.0f} -> {new_gross:,.0f} gross | net {new_net:,.0f}/mo (+{extra_net:,.0f}) | housing {new_pct:.0f}% | leftover {leftover:,.0f}/mo')
