-- =====================================================================
-- Claims BI - business questions answered in SQL
-- Each query is separated by  -- @name: <file>  so run_sql.py can export results.
-- Techniques: CTEs, joins across star schema, window functions (LAG, RANK,
-- running SUM, NTILE), CASE logic, conditional aggregation, date handling.
-- =====================================================================

-- @name: q01_executive_kpis
-- Q1. Headline KPIs for the executive scorecard.
WITH mm AS (SELECT COUNT(*) AS member_months FROM fact_member_months)
SELECT
    COUNT(*)                                                         AS total_claims,
    COUNT(DISTINCT member_id)                                        AS utilising_members,
    ROUND(SUM(billed_amount), 0)                                     AS total_billed,
    ROUND(SUM(paid_amount), 0)                                       AS total_paid,
    ROUND(SUM(paid_amount) / (SELECT member_months FROM mm), 2)      AS paid_pmpm,
    ROUND(100.0 * SUM(claim_status = 'Denied') / COUNT(*), 2)        AS denial_rate_pct,
    ROUND(AVG(turnaround_days), 1)                                   AS avg_turnaround_days,
    ROUND(100.0 * AVG(within_sla_flag), 2)                           AS pct_within_30d_sla
FROM fact_claims;

-- @name: q02_monthly_trend_mom
-- Q2. Monthly paid PMPM trend with month-over-month change (LAG).
WITH paid AS (
    SELECT substr(service_date, 1, 7) AS year_month, SUM(paid_amount) AS paid, COUNT(*) AS claims
    FROM fact_claims GROUP BY 1
), mm AS (
    SELECT year_month, COUNT(*) AS member_months FROM fact_member_months GROUP BY 1
)
SELECT p.year_month, p.claims, ROUND(p.paid, 0) AS paid, m.member_months,
       ROUND(p.paid / m.member_months, 2) AS paid_pmpm,
       ROUND(100.0 * (p.paid / m.member_months - LAG(p.paid / m.member_months) OVER (ORDER BY p.year_month))
             / LAG(p.paid / m.member_months) OVER (ORDER BY p.year_month), 1) AS pmpm_mom_pct
FROM paid p JOIN mm m USING (year_month)
ORDER BY p.year_month;

-- @name: q03_pmpm_by_line_of_business
-- Q3. Cost per member per month by line of business (right denominator = member months, not members).
WITH paid AS (
    SELECT plan_id, SUM(paid_amount) AS paid, COUNT(*) AS claims FROM fact_claims GROUP BY plan_id
), mm AS (
    SELECT plan_id, COUNT(*) AS member_months FROM fact_member_months GROUP BY plan_id
)
SELECT pl.line_of_business,
       SUM(mm.member_months)                                   AS member_months,
       SUM(paid.claims)                                        AS claims,
       ROUND(SUM(paid.paid) / SUM(mm.member_months), 2)        AS paid_pmpm,
       ROUND(1000.0 * 12 * SUM(paid.claims) / SUM(mm.member_months), 0) AS claims_per_1000_per_year
FROM dim_plan pl JOIN paid USING (plan_id) JOIN mm USING (plan_id)
GROUP BY pl.line_of_business
ORDER BY paid_pmpm DESC;

-- @name: q04_denials_by_network_specialty
-- Q4. Where are denials concentrated? Network status x specialty.
SELECT pr.network_status, pr.specialty,
       COUNT(*)                                                  AS claims,
       SUM(c.claim_status = 'Denied')                            AS denied,
       ROUND(100.0 * SUM(c.claim_status = 'Denied') / COUNT(*), 1) AS denial_rate_pct,
       ROUND(SUM(CASE WHEN c.claim_status = 'Denied' THEN c.allowed_amount END), 0) AS denied_allowed_value
FROM fact_claims c JOIN dim_provider pr USING (provider_id)
GROUP BY 1, 2
HAVING COUNT(*) >= 200
ORDER BY denial_rate_pct DESC;

-- @name: q05_denial_reasons
-- Q5. Top denial reasons and their share (window SUM for % of total).
SELECT denial_reason,
       COUNT(*) AS denied_claims,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_denials,
       ROUND(SUM(allowed_amount), 0) AS allowed_value_at_risk
FROM fact_claims
WHERE claim_status = 'Denied'
GROUP BY denial_reason
ORDER BY denied_claims DESC;

-- @name: q06_provider_ranking
-- Q6. Top 3 providers by paid amount within each specialty (RANK over partition).
WITH prov AS (
    SELECT pr.specialty, pr.provider_name, pr.network_status,
           COUNT(*) AS claims, ROUND(SUM(c.paid_amount), 0) AS paid,
           ROUND(AVG(c.paid_amount), 0) AS avg_paid_per_claim,
           ROUND(100.0 * SUM(c.claim_status = 'Denied') / COUNT(*), 1) AS denial_rate_pct
    FROM fact_claims c JOIN dim_provider pr USING (provider_id)
    GROUP BY pr.provider_id
)
SELECT * FROM (
    SELECT *, RANK() OVER (PARTITION BY specialty ORDER BY paid DESC) AS rank_in_specialty FROM prov
) WHERE rank_in_specialty <= 3
ORDER BY specialty, rank_in_specialty;

-- @name: q07_high_cost_claimants
-- Q7. Cost concentration: what share of spend comes from the top 1% / 5% of members? (NTILE + running total)
WITH member_cost AS (
    SELECT member_id, SUM(paid_amount) AS paid FROM fact_claims GROUP BY member_id
), ranked AS (
    SELECT member_id, paid, NTILE(100) OVER (ORDER BY paid DESC) AS pct_bucket FROM member_cost
)
SELECT 'Top 1% of members' AS cohort, ROUND(100.0 * SUM(CASE WHEN pct_bucket = 1 THEN paid END) / SUM(paid), 1) AS pct_of_total_paid FROM ranked
UNION ALL
SELECT 'Top 5% of members', ROUND(100.0 * SUM(CASE WHEN pct_bucket <= 5 THEN paid END) / SUM(paid), 1) FROM ranked
UNION ALL
SELECT 'Top 20% of members', ROUND(100.0 * SUM(CASE WHEN pct_bucket <= 20 THEN paid END) / SUM(paid), 1) FROM ranked;

-- @name: q08_chronic_vs_non_chronic
-- Q8. Do members with chronic conditions cost more? (drives care-management targeting)
WITH paid AS (
    SELECT m.chronic_condition_flag, SUM(c.paid_amount) AS paid
    FROM fact_claims c JOIN dim_member m USING (member_id) GROUP BY 1
), mm AS (
    SELECT m.chronic_condition_flag, COUNT(*) AS member_months
    FROM fact_member_months f JOIN dim_member m USING (member_id) GROUP BY 1
)
SELECT CASE chronic_condition_flag WHEN 1 THEN 'Chronic condition' ELSE 'No chronic condition' END AS cohort,
       member_months, ROUND(paid / member_months, 2) AS paid_pmpm
FROM paid JOIN mm USING (chronic_condition_flag);

-- @name: q09_turnaround_sla_by_claim_type
-- Q9. Operations: processing turnaround and 30-day SLA compliance by claim type.
SELECT claim_type,
       COUNT(*) AS processed_claims,
       ROUND(AVG(turnaround_days), 1) AS avg_tat_days,
       MAX(turnaround_days) AS max_tat_days,
       ROUND(100.0 * AVG(within_sla_flag), 1) AS pct_within_sla,
       SUM(within_sla_flag = 0) AS sla_breaches
FROM fact_claims
WHERE processed_date IS NOT NULL
GROUP BY claim_type
ORDER BY pct_within_sla;

-- @name: q10_seasonality
-- Q10. Seasonality: average monthly claim volume by calendar month (flu-season effect).
SELECT d.month_num, d.month_name,
       ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT d.year), 0) AS avg_claims_per_month
FROM fact_claims c JOIN dim_date d ON d.date_key = c.service_date_key
GROUP BY d.month_num, d.month_name
ORDER BY d.month_num;
