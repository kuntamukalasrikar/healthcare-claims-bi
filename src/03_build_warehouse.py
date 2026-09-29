"""
Step 3 - Transform clean data into a star schema, load it into SQLite
(the "warehouse"), and export the same tables as CSV for Power BI.
"""
from pathlib import Path
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, CLEAN = ROOT / "data" / "raw", ROOT / "data" / "clean"
PBI = ROOT / "powerbi" / "data"; PBI.mkdir(parents=True, exist_ok=True)
DB = ROOT / "data" / "claims_warehouse.db"
SLA_DAYS = 30
END = pd.Timestamp("2025-12-31")

claims = pd.read_csv(CLEAN / "claims_clean.csv", parse_dates=["service_date", "received_date", "processed_date"])
members = pd.read_csv(RAW / "members.csv", parse_dates=["enrollment_start", "enrollment_end"])
providers = pd.read_csv(RAW / "providers.csv", dtype={"npi": str})
plans = pd.read_csv(RAW / "plans.csv")

# ---- dim_member: derive age band
age = 2025 - members.birth_year
members["age_band"] = pd.cut(age, [-1, 17, 34, 49, 64, 200], labels=["0-17", "18-34", "35-49", "50-64", "65+"]).astype(str)
dim_member = members[["member_id", "gender", "birth_year", "age_band", "state", "plan_id",
                      "enrollment_start", "enrollment_end", "chronic_condition_flag"]]

# ---- dim_date
d = pd.DataFrame({"full_date": pd.date_range("2024-01-01", END)})
dim_date = pd.DataFrame({
    "date_key": d.full_date.dt.strftime("%Y%m%d").astype(int), "full_date": d.full_date.dt.date,
    "year": d.full_date.dt.year, "quarter": "Q" + d.full_date.dt.quarter.astype(str),
    "month_num": d.full_date.dt.month, "month_name": d.full_date.dt.strftime("%b"),
    "year_month": d.full_date.dt.strftime("%Y-%m"), "is_weekend": (d.full_date.dt.weekday >= 5).astype(int)})

# ---- fact_member_months (eligibility denominator for PMPM)
rows = []
for m in members.itertuples():
    end = m.enrollment_end if pd.notna(m.enrollment_end) else END
    for p in pd.period_range(m.enrollment_start, end, freq="M"):
        rows.append((m.member_id, m.plan_id, int(p.start_time.strftime("%Y%m%d")), str(p)))
fact_mm = pd.DataFrame(rows, columns=["member_id", "plan_id", "month_key", "year_month"])

# ---- fact_claims
f = claims.merge(members[["member_id", "plan_id"]], on="member_id", how="left")
f["service_date_key"] = f.service_date.dt.strftime("%Y%m%d").astype(int)
f["turnaround_days"] = (f.processed_date - f.received_date).dt.days
f["within_sla_flag"] = (f.turnaround_days <= SLA_DAYS).astype("Int64").where(f.processed_date.notna())
for c in ("service_date", "received_date", "processed_date"):
    f[c] = f[c].dt.date
fact_claims = f[["claim_id", "member_id", "provider_id", "plan_id", "service_date_key", "service_date",
                 "received_date", "processed_date", "claim_type", "diagnosis_code", "billed_amount",
                 "allowed_amount", "paid_amount", "member_responsibility", "claim_status", "denial_reason",
                 "turnaround_days", "within_sla_flag"]]
for col in ("enrollment_start", "enrollment_end"):
    dim_member[col] = dim_member[col].dt.date

# ---- load warehouse (schema from sql/00_schema.sql enforces PK/FK/CHECK constraints)
DB.unlink(missing_ok=True)
con = sqlite3.connect(DB)
con.execute("PRAGMA foreign_keys = ON")
con.executescript((ROOT / "sql" / "00_schema.sql").read_text())
tables = {"dim_plan": plans, "dim_member": dim_member, "dim_provider": providers,
          "dim_date": dim_date, "fact_claims": fact_claims, "fact_member_months": fact_mm}
for name, df in tables.items():
    df.to_sql(name, con, if_exists="append", index=False)
    df.to_csv(PBI / f"{name}.csv", index=False)
    print(f"{name:<20} {len(df):>8,} rows")
con.commit(); con.close()
