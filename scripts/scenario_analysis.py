"""Deposit & term scenario analysis — one-off script."""
import math

savings = 37500
rate = 4.5
bills = 211
ct_monthly = 125  # Band C estimate
take_home = 2650

def mortgage_payment(principal, rate_pct, term_years):
    r = (rate_pct / 100) / 12
    n = term_years * 12
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)

print("=" * 95)
print(f"DEPOSIT & TERM SCENARIO ANALYSIS  |  Savings: £{savings:,}  |  Rate: {rate}%  |  Take-home: £{take_home:,}/mo")
print(f"Bills: £{bills}/mo  |  CT Band C est: £{ct_monthly}/mo  |  GREEN cap: £1,006/mo  |  AMBER cap: £1,139/mo")
print(f"Assumes freehold (no SC/GR). Leasehold would add SC + GR on top.")
print("=" * 95)

deposits = [
    (37500, "All in (no buffer)"),
    (35000, "Keep £2.5k buffer"),
    (32500, "Keep £5k buffer"),
    (30000, "Keep £7.5k buffer"),
    (27500, "Keep £10k buffer (3-4mo expenses)"),
]

terms = [25, 30, 35]
prices = [150000, 160000, 170000, 180000, 190000]

for dep, dep_label in deposits:
    print(f"\n--- Deposit: £{dep:,} ({dep_label}) ---")
    header = f"{'Price':>10}  {'LTV':>5}  {'Term':>5}  {'Mortgage':>10}  {'Housing':>10}  {'All-in':>10}  {'Left':>8}  Status"
    print(header)
    print("-" * len(header))
    for price in prices:
        for term in terms:
            principal = price - dep
            if principal <= 0:
                continue
            ltv = (principal / price) * 100
            mtg = mortgage_payment(principal, rate, term)
            housing = mtg + ct_monthly
            all_in = housing + bills
            remaining = take_home - all_in
            if all_in <= 1006:
                status = "GREEN"
            elif all_in <= 1139:
                status = "AMBER"
            else:
                status = "RED"
            print(f"  £{price:>7,}  {ltv:>4.0f}%  {term:>3}yr  £{mtg:>8,.0f}/mo  £{housing:>8,.0f}/mo  £{all_in:>8,.0f}/mo  £{remaining:>5,.0f}  {status}")
    print()

print("=" * 95)
print("RECOMMENDATION:")
print("- Keep at least £5k-£7.5k as emergency fund (3+ months essential expenses)")
print("- 25yr term gives lowest total interest but highest monthly payments")
print("- 30yr term is a good middle ground — lower monthly, still reasonable total cost")
print("- 35yr term lowers monthly further but you pay significantly more interest overall")
print("=" * 95)
