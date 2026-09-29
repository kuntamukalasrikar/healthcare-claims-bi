# Power BI Build Guide (about 4–6 hours)

This is the part the job description weighs most heavily ("Experience developing Power BI dashboards and reports"), so build it yourself in **Power BI Desktop** (a free download for Windows). Everything it needs is in `powerbi/data/`.

---

## 1. Get the data in (Power Query)
1. **Get data → Text/CSV** and load all six files in `powerbi/data/` plus `outputs/dq_test_results.csv`.
2. In **Transform data** (Power Query), for each table:
   - Set the types: dates as **Date**, amounts as **Fixed decimal number**, IDs as **Text**, `npi` as **Text** (otherwise it loses its format).
   - In `fact_claims`, replace blanks in `denial_reason` with `"N/A"` for denied-only visuals. Leave `processed_date` blank for pending claims, because that blank means something.
   - Rename the steps (for example `Changed Type – amounts`). Interviewers like to see a readable Applied Steps list.
3. Close & Apply.

## 2. Model (star schema)
Open Model view and create these relationships. All are **one-to-many with single-direction filtering**:

| From (1) | To (*) |
|---|---|
| dim_member[member_id] | fact_claims[member_id] |
| dim_provider[provider_id] | fact_claims[provider_id] |
| dim_plan[plan_id] | fact_claims[plan_id] |
| dim_date[date_key] | fact_claims[service_date_key] |
| dim_member[member_id] | fact_member_months[member_id] |
| dim_plan[plan_id] | fact_member_months[plan_id] |
| dim_date[date_key] | fact_member_months[month_key] |

- Mark `dim_date` as the date table (`full_date`).
- Sort `dim_date[month_name]` by `month_num`.
- Hide the foreign-key columns in the fact tables so report users only drag fields from the dimensions.
- Add the measures from `DAX_measures.md`.
- Apply the theme: View → Themes → Browse → `claims_theme.json`.

## 3. Report pages

**Page 1 – Executive Overview**
- KPI cards: Total Paid, Paid PMPM, Member Months, Denial Rate %, SLA Compliance %
- Line chart: Paid PMPM by `year_month` (add a constant line for the average)
- Clustered bar: Paid PMPM by line of business
- Slicers: Year, Line of Business, State
- Dynamic title using `[Selected LOB Title]`

**Page 2 – Cost & Utilisation**
- Matrix: Specialty × Claim type → Total Paid, Avg Paid per Claim, Claims per 1,000
- Treemap: Paid by specialty
- Bar: Paid PMPM, chronic vs non-chronic members (`dim_member[chronic_condition_flag]`)
- Column: Paid PMPM by age band

**Page 3 – Denials & Revenue Leakage**
- Clustered bar: Denial Rate % by specialty, legend = network status
- Bar: Denied Claims by denial reason (sorted)
- Card: Denied Allowed $ at Risk
- Table: top providers by denial rate (use a Top N filter of 10 and require at least 100 claims with a visual-level filter)

**Page 4 – Claims Operations (SLA)**
- Gauge: SLA Compliance % (target 95%)
- Column: Avg Turnaround Days by claim type, with conditional colours
- Line: Pending claims by month
- Drill-through page: select a provider to see its claim-level detail

**Page 5 – Data Quality**
- Cards: DQ Tests Failed (Raw), DQ Pass Rate (Clean)
- Table from `dq_test_results`: test ID, rule, severity, rows failed, status (conditional icons: PASS green, FAIL red)
- Slicer: stage (RAW / CLEAN)

## 4. Extras worth adding (each one is an interview talking point)
- **Row-level security:** Modeling → Manage roles → role `State_TX` with filter `[state] = "TX"` on dim_member. Explain that regional managers see only their own members.
- **Bookmarks + buttons:** toggle between Paid and Allowed views.
- **Tooltip page:** hover over a specialty to see its mini trend.
- **Performance Analyzer:** record one refresh and note which visual is slowest (this lines up with "optimise dashboards for performance" in the job description).

## 5. Publish
- Save as `Claims_BI_Dashboard.pbix` in the repo's `powerbi/` folder.
- Export each page as PNG into `images/`, then update the README screenshots.
- Optional: **File → Publish to web** (free with a personal Power BI account). A live link on your resume stands out a lot more than a screenshot.

## Validate before you publish
Check that the cards match `outputs/sql_results/q01_executive_kpis.csv` (the table is at the bottom of `DAX_measures.md`).
