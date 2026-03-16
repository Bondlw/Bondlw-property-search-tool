# Property Search Tool — User Guide

## What This Tool Does

Every morning at 7:00 AM, the tool automatically:

1. Searches Rightmove for properties across 5 areas in the Tunbridge Wells cluster
2. Fetches the full details of each new listing (tenure, lease length, service charges, etc.)
3. Looks up crime statistics, supermarket distances, and commute times for each property
4. Checks every property against your criteria (budget, lease length, EPC, crime levels, etc.)
5. Scores qualifying properties out of 100 points
6. Generates an HTML report and opens it in your browser
7. Sends a Windows desktop notification (and email, if configured) summarising the results

The report is saved to `output\reports\` and named by date (e.g. `report_2026-03-15.html`). You can open any previous report from that folder at any time.

---

## How to Read the Daily Report

The report opens automatically in your browser after each run. It has several sections:

### Qualifying Properties

These are properties that passed **all** your hard criteria. They are sorted with new listings today at the top, then by score (highest first).

Each card shows:

- **Price and address** — with a link to the Rightmove listing
- **Score out of 100** — the weighted total across 6 categories (Financial Fit, Crime Safety, Cost Predictability, Layout, Walkability, Long-term)
- **Monthly cost** — the estimated all-in housing cost (mortgage + service charge + ground rent + council tax) with a Green/Amber/Red affordability indicator
- **Enrichment data** — nearest station and walk time, nearest supermarket and walk time, crime incidents per month, commute to London
- **Recommended offer** — a suggested offer price based on how long the property has been on the market and any previous price reductions
- **Gate results** — a list of all checks passed (and if applicable, the reasons something was flagged)
- **Financial breakdown** — a detailed cost table showing each component of the monthly cost
- **Price history** — a chart of price changes since first listed

### Favourites

Properties you have starred appear in their own section at the top of the report, regardless of whether they pass all gates. This is your shortlist.

### Opportunities

Properties that are close to qualifying but would need a negotiated offer to come within budget. These are only shown if:

- The only failing criteria are price/affordability (not safety, lease, or structural issues)
- A calculated offer price would bring the monthly cost into the Green target
- The property has been on the market for at least 30 days (suggesting the seller may be flexible)

Each opportunity card shows the suggested offer price and what the monthly cost would be at that price.

### Near Misses

Properties that failed one or more criteria but are worth being aware of. The most "liveable" failures (e.g. slightly over budget, EPC rating slightly low) are listed first. Near misses that appear in Opportunities are not duplicated here.

Common near-miss reasons:

- Monthly cost between Green (£795) and Amber (£928) ceiling — borderline affordable
- EPC rating unknown or below C — worth verifying
- Station slightly over 25 minutes walk
- Lease length just under the 120-year minimum

### New Today

A list of all properties seen for the first time today, regardless of which section they appear in. Useful for a quick scan of what came on the market overnight.

### Area Statistics

A table showing, per search area: total active listings, how many qualify, average price, average crime incidents per month, and average days on the market. Useful for comparing areas at a glance.

---

## How to Favourite a Property

**Option 1 — Using the web server (recommended):**

1. Run the serve command in a terminal:

   ```
   cd "C:\Users\liam.bond\Documents\Property Search Tool"
   python -m src serve
   ```

   The latest report opens automatically at `http://localhost:8765`.

2. Each property card has a star button. Click it to toggle the property as a favourite. The change saves to the database immediately — no need to refresh.

3. To regenerate the report with the updated favourites showing in the Favourites section, click the "Regenerate" button at the top of the page.

**Option 2 — Via CLI:**

You can view the property ID from the report (shown in small text on each card) and use:

```
python -m src status
```

The status command does not directly add favourites, but you can see property IDs there. The simplest method remains the web UI.

---

## How to Exclude a Property

Excluding a property hides it permanently from all report sections (qualifying, near misses, opportunities). Use this for properties you have reviewed and rejected.

**Option 1 — Via the web server:**

1. Start the server: `python -m src serve`
2. Click the "Exclude" button on a property card. You will be prompted for a reason.
3. The property disappears from the report on the next regeneration.
4. To undo: find the property in the excluded section of the report and click "Unexclude".

**Option 2 — Via CLI:**

```
python -m src exclude add <property_id> "reason here"
```

For example:

```
python -m src exclude add 42 "Leasehold with doubling ground rent clause"
python -m src exclude add 117 "Next to railway line, too noisy"
```

To undo an exclusion:

```
python -m src exclude remove 42
```

To see all current exclusions:

```
python -m src exclude list
```

---

## How to Adjust Your Search Criteria

All criteria are in `config\search_config.yaml`. Open it in any text editor (Notepad, VS Code, etc.).

### Changing Your Budget

Find the `budget` section:

```yaml
budget:
  freehold:
    ideal_min: 170000
    ideal_max: 180000
    responsible_max: 185000
    absolute_max: 190000
  leasehold:
    ideal_min: 150000
    ideal_max: 165000
    responsible_max: 170000
    absolute_max: 180000
```

- `absolute_max` is the hard price cap — no property above this amount will ever qualify.
- `responsible_max` is a softer cap — properties between responsible and absolute max are allowed only if the monthly cost stays within your Green target.

Also check the `monthly_target` section, which controls what counts as affordable:

```yaml
monthly_target:
  min: 795 # GREEN — housing ≤30% of take-home
  max: 928 # AMBER — housing ≤35% of take-home (ceiling for near misses)
```

If your take-home pay changes, update `user.monthly_take_home` as well.

### Changing Lease / Service Charge / Ground Rent Limits

Find the `hard_gates` section:

```yaml
hard_gates:
  lease_minimum_years: 120 # Standard leasehold
  sof_lease_minimum_years: 80 # Share of freehold (extension is cheap)
  service_charge_max_pa: 1200 # Annual service charge cap
  ground_rent_max_pa: 250 # Annual ground rent cap
  council_tax_max_band: "C" # Maximum council tax band
  epc_minimum_rating: "C" # Minimum EPC energy rating
  station_max_walk_min: 25 # Max walk to station (minutes)
  supermarket_max_walk_min: 30 # Max walk to supermarket (minutes)
```

Edit any value and save the file. The change takes effect on the next report generation (run `python -m src report` to regenerate immediately without scraping).

### Changing Crime Thresholds

```yaml
crime_thresholds:
  asb_monthly_max: 10
  burglary_monthly_max: 3
  drugs_monthly_max: 3
  violent_monthly_max: 8
```

Lower numbers are stricter. These are incidents per month within walking distance of the property, sourced from `data.police.uk`.

---

## How to Add or Remove Search Areas

Search areas are defined in `config\search_config.yaml` under `search_areas.primary` (and optionally `secondary`).

### Adding a New Area

1. Find the area's Rightmove ID. The easiest way is to search for the area on Rightmove, then look at the URL — it will contain something like `REGION^12345` or `STATION^5678`.

2. Add a new entry under `primary`:

```yaml
- name: "Borough Green"
  rightmove_id: "REGION^2580"
  zoopla_slug: "borough-green"
  lat: 51.2895
  lng: 0.3025
  miles_from_maidstone: 14
  train_to_london_min: 40
```

The `lat` and `lng` fields are the centre coordinates of the area — these are used for the area statistics table and the maximum radius filter. You can find them by searching the place name on Google Maps.

3. Save the file. The new area will be included in the next run.

### Removing an Area

Delete the relevant block from `search_areas.primary`. Or, to temporarily disable without deleting, you could move it to a `secondary` list and the tool will still include it (both primary and secondary are searched). To completely stop searching an area, remove its block.

### Excluding Specific Towns from Results

If properties from certain areas keep appearing in results but you never want to see them, add the town name to `excluded_address_terms`:

```yaml
excluded_address_terms:
  - maidstone
  - sevenoaks
  - tonbridge
  - monchelsea
```

Any property whose address contains one of these terms (case-insensitive) will be silently excluded from all report sections.

---

## How to Check If the Scheduler Is Running

**Via PowerShell:**

```powershell
Get-ScheduledTaskInfo -TaskName "PropertySearch_DailyRun" | Select-Object LastRunTime, LastTaskResult, NextRunTime
```

- `LastRunTime` — when it last ran
- `LastTaskResult` — `0` means success, anything else means it failed
- `NextRunTime` — when it will next run (should be tomorrow at 7:00 AM)

**Via Task Scheduler UI:**

1. Press Windows key, search for "Task Scheduler", open it
2. Click "Task Scheduler Library" in the left panel
3. Find "PropertySearch_DailyRun" in the list
4. Check the Status, Last Run Time, and Last Run Result columns

**Via the report files:**

Open `output\reports\` in File Explorer. If today's report (`report_YYYY-MM-DD.html`) exists, the run completed. If it is missing or outdated, the scheduler may not have run.

**Via the database run log:**

```
cd "C:\Users\liam.bond\Documents\Property Search Tool"
python -m src status
```

The bottom of the output shows the 5 most recent runs with timestamps and duration.

---

## Common Issues and Fixes

### No new properties found today

This is normal — some days there are simply no new listings. The report will still generate and show all active properties from previous days. "New today" being 0 is not an error.

If you consistently see 0 new properties for several days:

1. Check the Rightmove IDs in `config\search_config.yaml` are still valid (Rightmove occasionally changes region IDs).
2. Run `python -m src search` manually in a terminal and read the output.

### The report is not opening automatically

The tool tries to open the report in your default browser automatically. If it does not:

1. Open File Explorer and navigate to `output\reports\`
2. Double-click the latest `report_YYYY-MM-DD.html` file

Or run the server and use the browser:

```
python -m src serve
```

Then go to `http://localhost:8765` in your browser.

### The favourite/exclude buttons do nothing (from the static HTML file)

The interactive buttons only work when the server is running (`python -m src serve`). If you open the HTML file directly from File Explorer, the buttons cannot communicate with the database. Always use `python -m src serve` for interactive use.

### Properties are missing crime data or supermarket distances

Enrichment runs separately from scraping. New properties get their Rightmove details fetched first, then enrichment runs on the next full pipeline execution. A property will only appear without enrichment data on the day it is first found.

If a property has been around for several days and still shows no crime data:

1. Run `python -m src enrich --limit 5` manually
2. Check if it has coordinates (latitude/longitude) — enrichment requires them. If not, the detail fetch may have failed for that property.

### A property keeps appearing even though you excluded it

Exclusions only hide a property from the report — they do not delete it from the database. When you run `python -m src report` or the server's Regenerate function, excluded properties are filtered out before rendering.

If a property reappears after excluding:

1. Check with `python -m src exclude list` that the exclusion was saved
2. Regenerate the report: `python -m src report`

### The scheduler ran but no report was generated

1. Open `output\logs\scheduler.log` in a text editor to see the error output.
2. The most common causes are: Python path issue, dependency not installed, or the working directory not being set correctly.
3. Re-register the task by running `scripts\setup_scheduler.ps1` as Administrator, then try `Start-ScheduledTask -TaskName "PropertySearch_DailyRun"` to test.

### You want to see what a property looked like on a specific date

Reports are saved as separate HTML files per day in `output\reports\`. Open any previous report directly — the data in it reflects the database state at the time the report was generated.
