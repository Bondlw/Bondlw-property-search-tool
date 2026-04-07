print('=== QUERIPEL CLOSE PRICE ANALYSIS ===')
print()

print('LISTING FACTS:')
print('  Asking price: 179,950')
print('  Listed: 17 Feb 2026 (37 days on market)')
print('  Price reductions: NONE')
print('  Chain: NO CHAIN')
print('  Size: 542 sqft | 1 bed | Leasehold (900yr)')
print('  SC: 1,835/yr | GR: 137/yr')
print()

print('KEY COMPARABLE - SAME BUILDING:')
print('  Queripel Close (different unit): 200,000')
print('  559 sqft | Listed 20 Oct 2025 (157 days!)')
print('  Still unsold after 5+ months at 200k')
print()

comps = [
    ('Hunters Court, Showfields Rd', 155000, 330, 'leasehold'),
    ('Linden Gardens', 165000, 410, 'share_of_freehold'),
    ('North Farm Road', 170000, 402, 'share_of_freehold'),
    ('Glendale Court, Sandhurst Rd', 175000, 430, 'leasehold'),
    ('Hawthorn Walk', 177500, 430, 'leasehold'),
    ('QUERIPEL CLOSE (yours)', 179950, 542, 'leasehold'),
    ('Ferndale Close', 180000, 538, 'leasehold'),
    ('Hastings Road, Pembury', 180000, 527, 'leasehold'),
    ('Sherwood Road', 180000, 591, 'leasehold'),
    ('Chenies Close', 190000, 547, 'leasehold'),
    ('The Avenue', 190000, 512, 'leasehold'),
    ('Queripel Close (other unit)', 200000, 559, 'leasehold'),
]

print('TW 1-BED FLATS WITH SIZE DATA (price per sqft):')
for name, price, sqft, tenure in comps:
    ppsqft = price / sqft
    marker = ' <<<' if 'yours' in name.lower() else ''
    print(f'  {name:35s} {price:>8,} | {sqft:>4} sqft | {ppsqft:>6,.0f}/sqft | {tenure}{marker}')

tw_leasehold = [(p, s) for n, p, s, t in comps if 'yours' not in n.lower() and 'other' not in n.lower() and t == 'leasehold']
all_excl = [(p, s) for n, p, s, t in comps if 'yours' not in n.lower() and 'other' not in n.lower()]

avg_ppsqft_lh = sum(p/s for p, s in tw_leasehold) / len(tw_leasehold)
avg_ppsqft_all = sum(p/s for p, s in all_excl) / len(all_excl)

print()
print(f'  Avg price/sqft (leasehold only): {avg_ppsqft_lh:,.0f}/sqft')
print(f'  Avg price/sqft (all comparables): {avg_ppsqft_all:,.0f}/sqft')
print(f'  Queripel at asking (179,950):     {179950/542:,.0f}/sqft')

fair_lh = avg_ppsqft_lh * 542
fair_all = avg_ppsqft_all * 542
print()
print(f'  Queripel fair value (leasehold avg): {fair_lh:,.0f}')
print(f'  Queripel fair value (all avg):       {fair_all:,.0f}')

print()
print('=== OFFER STRATEGY ===')
print()
offers = [
    (175000, 'Token negotiation'),
    (170000, 'Reasonable 1st offer'),
    (167500, 'Solid opening'),
    (165000, 'Lowest respectful'),
    (160000, 'Cheeky - risks offence'),
    (155000, 'Insulting territory'),
]
header = f'  {"Offer":>8s} | {"Discount":>8s} | Signal'
print(header)
print(f'  --------+----------+------')
for offer, signal in offers:
    discount = (179950 - offer) / 179950 * 100
    print(f'  {offer:>8,} |   {discount:>5.1f}% | {signal}')
