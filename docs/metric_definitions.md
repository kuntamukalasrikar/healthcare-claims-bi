# Metric Definitions & Business Rules

This is the single source of truth. SQL (`sql/01_kpi_analysis.sql`), DAX (`powerbi/DAX_measures.md`) and the Excel pack all use these definitions.

## Metrics

| Metric | Definition | Formula | Grain / notes |
|---|---|---|---|
| Total Claims | Count of adjudicated claim records loaded to the warehouse | `COUNT(claim_id)` | Excludes quarantined and duplicate rows |
| Total Billed | Amount the provider charged | `SUM(billed_amount)` | |
| Total Allowed | Contracted amount the plan recognises | `SUM(allowed_amount)` | Always ≤ billed |
| Total Paid | Amount the plan paid | `SUM(paid_amount)` | Denied and pending claims = 0 |
| Member Months | One member enrolled for one month | `COUNT(*)` on fact_member_months | The denominator for every "per member" metric |
| Paid PMPM | Paid per member per month | `Total Paid / Member Months` | The industry-standard cost metric. Never divide by distinct members |
| Claims per 1,000 | Annualised utilisation rate | `Claims × 12 × 1000 / Member Months` | |
| Denial Rate % | Share of claims denied | `Denied Claims / Total Claims` | Includes pending in the denominator |
| Denied Allowed $ at Risk | Allowed value of denied claims | `SUM(allowed_amount) WHERE status = 'Denied'` | A proxy for provider-abrasion / appeal exposure |
| Turnaround Days | Days from receipt to adjudication | `processed_date − received_date` | Pending claims excluded |
| SLA Compliance % | Share of processed claims finalised within 30 days | `AVG(within_sla_flag)` | The 30-day clean-claim standard |

## Business rules applied during cleansing

| Rule | Description | Action |
|---|---|---|
| BR-01 | A claim_id must be unique | Exact duplicates are removed. Same ID with different values goes to **quarantine** |
| BR-02 | Every claim must link to an eligible member and a known provider | Orphans are **quarantined** and returned to the source-system owner |
| BR-03 | billed_amount > 0 and paid ≤ allowed ≤ billed | Violations are **quarantined** |
| BR-04 | A denied claim cannot carry a payment | paid_amount is **corrected** to 0 and logged |
| BR-05 | claim_status ∈ {Paid, Denied, Pending} | Casing and whitespace are **standardised** |
| BR-06 | Dates must follow service ≤ received ≤ processed, with no future dates | Violations are **quarantined** |
| BR-07 | diagnosis_code must be valid ICD-10 format | Invalid codes are **mapped** to R69 ("Illness, unspecified") and logged |

Every raw row is accounted for: `raw = duplicates removed + quarantined + loaded`. See `outputs/dq_reconciliation.csv`.

## Known limitations
- The most recent month (Dec 2025) is incomplete because of claims run-out lag. Exclude it from trend conclusions or flag it on the report.
- The data is synthetic. Patterns were designed to be realistic but are not real payer benchmarks.
