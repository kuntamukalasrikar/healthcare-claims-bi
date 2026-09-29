"""Generate a TMDL script (Power BI Desktop > TMDL view) that creates the whole semantic model:
tables (Power Query sources + types), relationships, date table and all DAX measures."""
import sys
BASE = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\kunta\Documents\healthcare-claims-bi"
T = "\t"

# column: (M type, TMDL dataType, extra props)
TABLES = {
    "dim_plan": [("plan_id", "text"), ("plan_name", "text"), ("line_of_business", "text"), ("monthly_premium", "cur")],
    "dim_member": [("member_id", "text"), ("gender", "text"), ("birth_year", "int_key"), ("age_band", "text"), ("state", "text"),
                   ("plan_id", "text"), ("enrollment_start", "date"), ("enrollment_end", "date"), ("chronic_condition_flag", "int_key")],
    "dim_provider": [("provider_id", "text"), ("npi", "text"), ("provider_name", "text"), ("specialty", "text"),
                     ("network_status", "text"), ("state", "text")],
    "dim_date": [("date_key", "int_key"), ("full_date", "date"), ("year", "int_key"), ("quarter", "text"), ("month_num", "int_key"),
                 ("month_name", "text"), ("year_month", "text"), ("is_weekend", "int_key")],
    "fact_claims": [("claim_id", "text"), ("member_id", "text"), ("provider_id", "text"), ("plan_id", "text"),
                    ("service_date_key", "int_key"), ("service_date", "date"), ("received_date", "date"), ("processed_date", "date"),
                    ("claim_type", "text"), ("diagnosis_code", "text"), ("billed_amount", "cur"), ("allowed_amount", "cur"),
                    ("paid_amount", "cur"), ("member_responsibility", "cur"), ("claim_status", "text"), ("denial_reason", "text"),
                    ("turnaround_days", "num"), ("within_sla_flag", "int")],
    "fact_member_months": [("member_id", "text"), ("plan_id", "text"), ("month_key", "int_key"), ("year_month", "text")],
    "dq_test_results": [("stage", "text"), ("test_case_id", "text"), ("column", "text"), ("rule", "text"), ("severity", "text"),
                        ("expected", "text"), ("actual", "text"), ("rows_failed", "int"), ("pct_failed", "num"), ("status", "text")],
}
MTYPE = {"text": "type text", "cur": "Currency.Type", "int": "Int64.Type", "int_key": "Int64.Type", "date": "type date", "num": "type number"}
DTYPE = {"text": "string", "cur": "decimal", "int": "int64", "int_key": "int64", "date": "dateTime", "num": "double"}
HIDDEN = {("fact_claims", c) for c in ("member_id", "provider_id", "plan_id", "service_date_key")} | \
         {("fact_member_months", c) for c in ("member_id", "plan_id", "month_key")}

MEASURES = [
    ("Total Claims", "COUNTROWS ( fact_claims )", "#,0"),
    ("Total Billed", "SUM ( fact_claims[billed_amount] )", "\\$#,0"),
    ("Total Allowed", "SUM ( fact_claims[allowed_amount] )", "\\$#,0"),
    ("Total Paid", "SUM ( fact_claims[paid_amount] )", "\\$#,0"),
    ("Member Months", "COUNTROWS ( fact_member_months )", "#,0"),
    ("Paid PMPM", "DIVIDE ( [Total Paid], [Member Months] )", "\\$#,0.00"),
    ("Claims per 1000", "DIVIDE ( [Total Claims] * 12 * 1000, [Member Months] )", "#,0"),
    ("Avg Paid per Claim", "DIVIDE ( [Total Paid], [Total Claims] )", "\\$#,0"),
    ("Discount from Billed %", "1 - DIVIDE ( [Total Allowed], [Total Billed] )", "0.0%"),
    ("Denied Claims", "CALCULATE ( [Total Claims], fact_claims[claim_status] = \"Denied\" )", "#,0"),
    ("Denial Rate %", "DIVIDE ( [Denied Claims], [Total Claims] )", "0.00%"),
    ("Denied Allowed $ at Risk", "CALCULATE ( [Total Allowed], fact_claims[claim_status] = \"Denied\" )", "\\$#,0"),
    ("Out-of-Network Denial Rate %", "CALCULATE ( [Denial Rate %], dim_provider[network_status] = \"Out-of-Network\" )", "0.0%"),
    ("Avg Turnaround Days", "AVERAGE ( fact_claims[turnaround_days] )", "0.0"),
    ("SLA Compliance %", "DIVIDE ( CALCULATE ( [Total Claims], fact_claims[within_sla_flag] = 1 ), CALCULATE ( [Total Claims], NOT ISBLANK ( fact_claims[processed_date] ) ) )", "0.00%"),
    ("Pending Claims", "CALCULATE ( [Total Claims], fact_claims[claim_status] = \"Pending\" )", "#,0"),
    ("Paid PMPM PM", "CALCULATE ( [Paid PMPM], DATEADD ( dim_date[full_date], -1, MONTH ) )", "\\$#,0.00"),
    ("Paid PMPM MoM %", "DIVIDE ( [Paid PMPM] - [Paid PMPM PM], [Paid PMPM PM] )", "0.0%"),
    ("Total Paid YTD", "TOTALYTD ( [Total Paid], dim_date[full_date] )", "\\$#,0"),
    ("Total Paid PY", "CALCULATE ( [Total Paid], SAMEPERIODLASTYEAR ( dim_date[full_date] ) )", "\\$#,0"),
    ("Total Paid YoY %", "DIVIDE ( [Total Paid] - [Total Paid PY], [Total Paid PY] )", "0.0%"),
    ("KPI Colour Denial", "SWITCH ( TRUE (), [Denial Rate %] > 0.15, \"#C0392B\", [Denial Rate %] > 0.10, \"#D9822B\", \"#2E7D32\" )", None),
    ("Selected LOB Title", "\"Claims Performance - \" & SELECTEDVALUE ( dim_plan[line_of_business], \"All Lines of Business\" )", None),
    ("DQ Tests Failed (Raw)", "CALCULATE ( COUNTROWS ( dq_test_results ), dq_test_results[stage] = \"RAW\", dq_test_results[status] = \"FAIL\" )", "0"),
    ("DQ Tests Passed (Clean)", "CALCULATE ( COUNTROWS ( dq_test_results ), dq_test_results[stage] = \"CLEAN\", dq_test_results[status] = \"PASS\" )", "0"),
    ("DQ Pass Rate (Clean)", "DIVIDE ( [DQ Tests Passed (Clean)], CALCULATE ( COUNTROWS ( dq_test_results ), dq_test_results[stage] = \"CLEAN\" ) )", "0%"),
]

RELS = [("fact_claims.member_id", "dim_member.member_id"), ("fact_claims.provider_id", "dim_provider.provider_id"),
        ("fact_claims.plan_id", "dim_plan.plan_id"), ("fact_claims.service_date_key", "dim_date.date_key"),
        ("fact_member_months.member_id", "dim_member.member_id"), ("fact_member_months.plan_id", "dim_plan.plan_id"),
        ("fact_member_months.month_key", "dim_date.date_key")]


def q(name):
    return f"'{name}'" if any(ch in name for ch in " %$()-.,") else name


out = ["createOrReplace", ""]
for tbl, cols in TABLES.items():
    out.append(f"{T}table {tbl}")
    if tbl == "dim_date":
        out.append(f"{T*2}dataCategory: Time")
    out.append("")
    for c, k in cols:
        out.append(f"{T*2}column {q(c)}")
        out.append(f"{T*3}dataType: {DTYPE[k]}")
        if k == "date":
            out.append(f"{T*3}formatString: yyyy-mm-dd")
        if k == "cur":
            out.append(f"{T*3}formatString: \\$#,0.00")
        if k in ("text", "int_key", "date") or (tbl, c) in HIDDEN:
            out.append(f"{T*3}summarizeBy: none")
        if (tbl, c) in HIDDEN:
            out.append(f"{T*3}isHidden")
        if tbl == "dim_date" and c == "full_date":
            out.append(f"{T*3}isKey")
        if tbl == "dim_date" and c == "month_name":
            out.append(f"{T*3}sortByColumn: month_num")
        out.append(f"{T*3}sourceColumn: {c}")
        out.append("")
    types = ", ".join(f'{{"{c}", {MTYPE[k]}}}' for c, k in cols)
    path = BASE + "\\" + tbl + ".csv"
    out += [f"{T*2}partition {tbl} = m", f"{T*3}mode: import", f"{T*3}source =",
            f"{T*5}let",
            f'{T*6}Source = Csv.Document(File.Contents("{path}"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
            f"{T*6}Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
            f'{T*6}Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")',
            f"{T*5}in", f"{T*6}Typed", ""]

out += [f"{T}table _Measures", ""]
for name, expr, fmt in MEASURES:
    out.append(f"{T*2}measure {q(name)} = {expr}")
    if fmt:
        out.append(f"{T*3}formatString: {fmt}")
    out.append("")
out += [f"{T*2}column Placeholder", f"{T*3}dataType: string", f"{T*3}isHidden", f"{T*3}summarizeBy: none",
        f"{T*3}sourceColumn: Placeholder", "",
        f"{T*2}partition _Measures = m", f"{T*3}mode: import", f"{T*3}source =",
        f"{T*5}#table(type table [Placeholder = text], {{}})", ""]

for i, (a, b) in enumerate(RELS, 1):
    out += [f"{T}relationship rel_{a.replace('.', '_')}", f"{T*2}fromColumn: {a}", f"{T*2}toColumn: {b}", ""]

open(sys.argv[2] if len(sys.argv) > 2 else "model.tmdl", "w", newline="\r\n").write("\n".join(out))
print(f"{len(TABLES)} tables, {len(MEASURES)} measures, {len(RELS)} relationships")
