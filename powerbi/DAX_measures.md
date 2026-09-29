# DAX Measures

Create a blank table called `_Measures` (Home → Enter data → name it `_Measures`) and add these measures to it, so all KPIs live in one place.
Every measure matches a definition in `docs/metric_definitions.md`. That's how the "consistent metrics across reports" requirement is met.

## Volume and cost

```DAX
Total Claims = COUNTROWS ( fact_claims )

Total Billed = SUM ( fact_claims[billed_amount] )

Total Allowed = SUM ( fact_claims[allowed_amount] )

Total Paid = SUM ( fact_claims[paid_amount] )

Member Months = COUNTROWS ( fact_member_months )

Paid PMPM = DIVIDE ( [Total Paid], [Member Months] )

Claims per 1,000 (Annualised) = DIVIDE ( [Total Claims] * 12 * 1000, [Member Months] )

Avg Paid per Claim = DIVIDE ( [Total Paid], [Total Claims] )

Discount from Billed % = 1 - DIVIDE ( [Total Allowed], [Total Billed] )
```

## Denials

```DAX
Denied Claims =
CALCULATE ( [Total Claims], fact_claims[claim_status] = "Denied" )

Denial Rate % = DIVIDE ( [Denied Claims], [Total Claims] )

Denied Allowed $ at Risk =
CALCULATE ( [Total Allowed], fact_claims[claim_status] = "Denied" )

Out-of-Network Denial Rate % =
CALCULATE ( [Denial Rate %], dim_provider[network_status] = "Out-of-Network" )
```

## Operations and SLA

```DAX
Avg Turnaround Days = AVERAGE ( fact_claims[turnaround_days] )

SLA Compliance % =
DIVIDE (
    CALCULATE ( [Total Claims], fact_claims[within_sla_flag] = 1 ),
    CALCULATE ( [Total Claims], NOT ISBLANK ( fact_claims[processed_date] ) )
)

Pending Claims = CALCULATE ( [Total Claims], fact_claims[claim_status] = "Pending" )
```

## Time intelligence
Needs `dim_date` to be marked as a date table: select dim_date → Table tools → Mark as date table → `full_date`.

```DAX
Paid PMPM PM =
CALCULATE ( [Paid PMPM], DATEADD ( dim_date[full_date], -1, MONTH ) )

Paid PMPM MoM % = DIVIDE ( [Paid PMPM] - [Paid PMPM PM], [Paid PMPM PM] )

Total Paid YTD = TOTALYTD ( [Total Paid], dim_date[full_date] )

Total Paid PY =
CALCULATE ( [Total Paid], SAMEPERIODLASTYEAR ( dim_date[full_date] ) )

Total Paid YoY % = DIVIDE ( [Total Paid] - [Total Paid PY], [Total Paid PY] )
```

## Dynamic titles and conditional formatting

```DAX
KPI Colour Denial =
SWITCH ( TRUE (), [Denial Rate %] > 0.15, "#C0392B", [Denial Rate %] > 0.10, "#D9822B", "#2E7D32" )

Selected LOB Title =
"Claims Performance – " & SELECTEDVALUE ( dim_plan[line_of_business], "All Lines of Business" )
```

## Data-quality page (built from outputs/dq_test_results.csv)

```DAX
DQ Tests Failed (Raw) =
CALCULATE ( COUNTROWS ( dq_test_results ), dq_test_results[stage] = "RAW", dq_test_results[status] = "FAIL" )

DQ Tests Passed (Clean) =
CALCULATE ( COUNTROWS ( dq_test_results ), dq_test_results[stage] = "CLEAN", dq_test_results[status] = "PASS" )

DQ Pass Rate (Clean) =
DIVIDE ( [DQ Tests Passed (Clean)], CALCULATE ( COUNTROWS ( dq_test_results ), dq_test_results[stage] = "CLEAN" ) )
```

## Check your numbers against SQL
With no filters applied, your cards should show exactly the numbers from `outputs/sql_results/q01_executive_kpis.csv`:

| Measure | Expected |
|---|---|
| Total Claims | 58,922 |
| Total Paid | $53,901,495 |
| Paid PMPM | $343.33 |
| Denial Rate % | 9.86% |
| SLA Compliance % | 96.68% |

If any of these don't match, check the relationship or measure before you publish. This is the same reconciliation habit as checking an API response against the expected payload.
