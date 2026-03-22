"""Audit all favourited properties against hard gates from config."""
import sqlite3
import yaml

conn = sqlite3.connect('data/property_search.db')
cur = conn.cursor()

with open('config/search_config.yaml', 'r') as f:
    config = yaml.safe_load(f)
gates = config['hard_gates']
budget = config['budget']

cur.execute('''
    SELECT f.id, p.id, p.address, p.price, p.tenure, p.property_type, p.bedrooms,
           p.lease_years, p.service_charge_pa, p.ground_rent_pa, 
           p.council_tax_band, p.epc_rating,
           e.nearest_station_walk_min, e.nearest_supermarket_walk_min,
           e.flood_zone, e.nearest_station_name
    FROM favourites f
    JOIN properties p ON p.id = f.property_id
    LEFT JOIN enrichment_data e ON e.property_id = p.id
    ORDER BY p.tenure, p.price
''')

rows = cur.fetchall()
band_order = {'A':1,'B':2,'C':3,'D':4,'E':5,'F':6,'G':7,'H':8}
epc_order = {'A':1,'B':2,'C':3,'D':4,'E':5,'F':6,'G':7}

pass_ids = []
fail_ids = []

for row in rows:
    fav_id, prop_id, address, price, tenure, ptype, beds = row[:7]
    lease_yrs, sc_pa, gr_pa, ct_band, epc = row[7:12]
    station_walk, supermarket_walk, flood_zone, station_name = row[12:]
    
    fails = []
    warnings = []
    
    # Station walk
    if station_walk is not None:
        if station_walk > gates['station_max_walk_min']:
            fails.append("station %dmin > %dmin max" % (int(station_walk), gates['station_max_walk_min']))
    else:
        warnings.append('no station data')
    
    # Supermarket walk
    if supermarket_walk is not None:
        if supermarket_walk > gates['supermarket_max_walk_min']:
            fails.append("supermarket %dmin > %dmin max" % (int(supermarket_walk), gates['supermarket_max_walk_min']))
    
    # Council tax band
    if ct_band:
        ct = ct_band.upper().strip()
        max_ct = gates['council_tax_max_band'].upper()
        if ct in band_order and max_ct in band_order:
            if band_order[ct] > band_order[max_ct]:
                fails.append("CT band %s > max %s" % (ct, max_ct))
    else:
        warnings.append('no CT band')
    
    # EPC
    if epc:
        e = epc.upper().strip()
        min_epc = gates['epc_minimum_rating'].upper()
        if e in epc_order and min_epc in epc_order:
            if epc_order[e] > epc_order[min_epc]:
                fails.append("EPC %s < min %s" % (e, min_epc))
    else:
        warnings.append('no EPC')
    
    # Lease years
    t = (tenure or '').lower()
    if t == 'leasehold':
        if lease_yrs is not None:
            if lease_yrs < gates['lease_absolute_minimum_years']:
                fails.append("lease %dyr < %dyr absolute min" % (lease_yrs, gates['lease_absolute_minimum_years']))
            elif lease_yrs < gates['lease_minimum_years']:
                warnings.append("lease %dyr < %dyr ideal" % (lease_yrs, gates['lease_minimum_years']))
        else:
            warnings.append('no lease years data')
    elif 'share' in t or 'sof' in t:
        if lease_yrs is not None and lease_yrs < gates['sof_lease_minimum_years']:
            fails.append("SoF lease %dyr < %dyr min" % (lease_yrs, gates['sof_lease_minimum_years']))
    
    # Service charge
    if sc_pa is not None:
        if sc_pa > gates['service_charge_max_pa']:
            fails.append("SC %d/yr > max %d" % (sc_pa, gates['service_charge_max_pa']))
        elif sc_pa > gates['service_charge_ideal_pa']:
            warnings.append("SC %d/yr > ideal %d" % (sc_pa, gates['service_charge_ideal_pa']))
    
    # Ground rent
    if gr_pa is not None:
        if gr_pa > gates['ground_rent_max_pa']:
            fails.append("GR %d/yr > max %d" % (gr_pa, gates['ground_rent_max_pa']))
        elif gr_pa > gates['ground_rent_ideal_pa']:
            warnings.append("GR %d/yr > ideal %d" % (gr_pa, gates['ground_rent_ideal_pa']))
    
    # Bedrooms
    if beds is not None and beds < gates['min_bedrooms']:
        fails.append("%d beds < min %d" % (beds, gates['min_bedrooms']))
    
    # Budget
    search_max = budget.get('search_max', 200000)
    if price is not None and price > search_max:
        fails.append("price %d > max %d" % (price, search_max))
    
    status = 'PASS' if not fails else 'FAIL'
    if fails:
        fail_ids.append((fav_id, prop_id, address))
    else:
        pass_ids.append((fav_id, prop_id, address))
    warn_str = " [%d warns]" % len(warnings) if warnings else ""
    
    stn_str = "%s (%dmin)" % (station_name, int(station_walk)) if station_name and station_walk else "no data"
    ct_str = ct_band or "?"
    epc_str = epc or "?"
    lease_str = "%dyr" % lease_yrs if lease_yrs else "n/a"
    sc_str = "%d" % sc_pa if sc_pa is not None else "?"
    gr_str = "%d" % gr_pa if gr_pa is not None else "?"
    
    print()
    print("  %s%s | %7s | %-20s | %s" % (status, warn_str, "{:,}".format(price), tenure, address))
    print("    Stn: %-35s | CT: %s | EPC: %s | Lease: %s | SC: %s | GR: %s" % (stn_str, ct_str, epc_str, lease_str, sc_str, gr_str))
    for f in fails:
        print("    FAIL: %s" % f)
    for w in warnings:
        print("    WARN: %s" % w)

print()
print("=" * 60)
print("Summary: %d PASS, %d FAIL out of %d favourites" % (len(pass_ids), len(fail_ids), len(rows)))
print("=" * 60)

if fail_ids:
    print()
    print("FAILING FAVOURITES (fav_id, prop_id, address):")
    for fav_id, prop_id, address in fail_ids:
        print("  fav=%d  prop=%d  %s" % (fav_id, prop_id, address))

conn.close()
