"""
Step 2 - Data-quality validation & cleansing.

Built the way a QA engineer writes API test cases: every rule has a Test Case ID,
a severity, an expected result and an actual result, and ends PASS or FAIL.
The suite runs twice:
  1. against the RAW extract   -> finds the defects (baseline DQ report)
  2. against the CLEAN output  -> proves the fixes worked (regression run)

Critical failures are quarantined (kept aside with the failure reason, never
silently deleted) so they can be sent back to the source-system owner.
"""
from pathlib import Path
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, CLEAN, OUT = ROOT / "data" / "raw", ROOT / "data" / "clean", ROOT / "outputs"
CLEAN.mkdir(parents=True, exist_ok=True); OUT.mkdir(parents=True, exist_ok=True)
REPORT_DATE = pd.Timestamp("2025-12-31")
VALID_STATUS = {"Paid", "Denied", "Pending"}
ICD10 = re.compile(r"^[A-Z][0-9][0-9A-Z](\.[0-9A-Z]{1,4})?$")


def load():
    c = pd.read_csv(RAW / "claims_raw.csv", dtype={"member_id": str, "provider_id": str})
    for col in ("service_date", "received_date", "processed_date"):
        c[col] = pd.to_datetime(c[col], errors="coerce")
    return (c, pd.read_csv(RAW / "members.csv"), pd.read_csv(RAW / "providers.csv"),
            pd.read_csv(RAW / "plans.csv"))


def test_suite(c, members, providers):
    """Each test returns a boolean mask of FAILING rows."""
    return [
        # id, table.column, rule, severity, fail-mask
        ("DQ-01", "claims.claim_id", "claim_id is unique (no duplicate submissions)", "Critical",
         c.claim_id.duplicated(keep="first")),
        ("DQ-02", "claims.claim_id", "claim_id is not null", "Critical", c.claim_id.isna()),
        ("DQ-03", "claims.member_id", "member_id exists in members (referential integrity)", "Critical",
         ~c.member_id.isin(members.member_id)),
        ("DQ-04", "claims.provider_id", "provider_id is not null", "Critical", c.provider_id.isna()),
        ("DQ-05", "claims.provider_id", "provider_id exists in providers", "High",
         c.provider_id.notna() & ~c.provider_id.isin(providers.provider_id)),
        ("DQ-06", "claims.billed_amount", "billed_amount > 0", "Critical", ~(c.billed_amount > 0)),
        ("DQ-07", "claims.paid_amount", "paid_amount <= allowed_amount <= billed_amount", "High",
         (c.paid_amount > c.allowed_amount + 0.01) | (c.allowed_amount > c.billed_amount.abs() + 0.01)),
        ("DQ-08", "claims.claim_status", "claim_status in allowed list {Paid, Denied, Pending}", "Medium",
         ~c.claim_status.isin(VALID_STATUS)),
        ("DQ-09", "claims.paid_amount", "Denied claims have paid_amount = 0", "High",
         c.claim_status.str.strip().str.title().eq("Denied") & (c.paid_amount > 0)),
        ("DQ-10", "claims.denial_reason", "Denied claims carry a denial_reason", "Medium",
         c.claim_status.str.strip().str.title().eq("Denied") & c.denial_reason.isna()),
        ("DQ-11", "claims.service_date", "service_date not in the future", "Critical",
         c.service_date > REPORT_DATE),
        ("DQ-12", "claims.processed_date", "processed_date >= received_date", "High",
         c.processed_date.notna() & (c.processed_date < c.received_date)),
        ("DQ-13", "claims.received_date", "received_date >= service_date", "High",
         c.received_date < c.service_date),
        ("DQ-14", "claims.diagnosis_code", "diagnosis_code matches ICD-10 format", "Medium",
         ~c.diagnosis_code.astype(str).str.match(ICD10)),
        ("DQ-15", "claims.processed_date", "Pending claims have no processed_date", "Low",
         c.claim_status.str.strip().str.title().eq("Pending") & c.processed_date.notna()),
    ]


def run(c, members, providers, stage):
    rows = []
    for tc, col, rule, sev, mask in test_suite(c, members, providers):
        n = int(mask.sum())
        rows.append({"stage": stage, "test_case_id": tc, "column": col, "rule": rule, "severity": sev,
                     "expected": "0 failing rows", "actual": f"{n} failing rows",
                     "rows_failed": n, "pct_failed": round(n / len(c) * 100, 3),
                     "status": "PASS" if n == 0 else "FAIL"})
    return pd.DataFrame(rows)


def cleanse(c, members, providers):
    log, quarantine = [], []
    c = c.copy()

    def q(mask, reason):
        bad = c[mask].copy(); bad["quarantine_reason"] = reason
        quarantine.append(bad); log.append((reason, "quarantined", int(mask.sum())))
        return c[~mask]

    n0 = len(c)
    c = c.drop_duplicates(keep="first"); log.append(("Exact duplicate rows", "removed", n0 - len(c)))
    c = q(c.claim_id.duplicated(keep="first"), "Duplicate claim_id with different values")
    # fixable: standardise codes
    fix = ~c.claim_status.isin(VALID_STATUS)
    c["claim_status"] = c.claim_status.str.strip().str.title(); log.append(("Status casing/whitespace", "standardised", int(fix.sum())))
    # critical: cannot be trusted -> quarantine and return to source
    c = q(~c.member_id.isin(members.member_id), "Orphan member_id (not in eligibility)")
    c = q(c.provider_id.isna() | ~c.provider_id.isin(providers.provider_id), "Missing/unknown provider_id")
    c = q(~(c.billed_amount > 0), "Non-positive billed_amount")
    c = q(c.service_date > REPORT_DATE, "Future service_date")
    c = q(c.processed_date.notna() & (c.processed_date < c.received_date), "processed_date before received_date")
    c = q(c.paid_amount > c.allowed_amount + 0.01, "paid_amount exceeds allowed_amount")
    # fixable by business rule
    m = c.claim_status.eq("Denied") & (c.paid_amount > 0)
    c.loc[m, "paid_amount"] = 0.0; log.append(("Denied claim with paid_amount > 0 (set to 0 per rule BR-04)", "corrected", int(m.sum())))
    m = ~c.diagnosis_code.astype(str).str.match(ICD10)
    c.loc[m, "diagnosis_code"] = "R69"; log.append(("Invalid ICD-10 code mapped to R69 'Unspecified'", "corrected", int(m.sum())))
    return c.reset_index(drop=True), pd.concat(quarantine), pd.DataFrame(log, columns=["issue", "action", "rows"])


if __name__ == "__main__":
    claims, members, providers, plans = load()
    before = run(claims, members, providers, "RAW")
    clean, quarantine, log = cleanse(claims, members, providers)
    after = run(clean, members, providers, "CLEAN")

    # reconciliation: every raw row is accounted for (like verifying an API response count)
    dupes = int(log.loc[log.issue.eq("Exact duplicate rows"), "rows"].sum())
    recon = pd.DataFrame([
        ("Raw rows received", len(claims)), ("Exact duplicates removed", dupes),
        ("Rows quarantined", len(quarantine)), ("Rows loaded to warehouse", len(clean)),
        ("Reconciles (raw = dupes + quarantined + loaded)", str(len(claims) == dupes + len(quarantine) + len(clean))),
    ], columns=["check", "value"])

    pd.concat([before, after]).to_csv(OUT / "dq_test_results.csv", index=False)
    log.to_csv(OUT / "dq_cleansing_log.csv", index=False)
    recon.to_csv(OUT / "dq_reconciliation.csv", index=False)
    quarantine.to_csv(OUT / "quarantined_claims.csv", index=False)
    clean.to_csv(CLEAN / "claims_clean.csv", index=False)

    print(before[["test_case_id", "rule", "severity", "rows_failed", "status"]].to_string(index=False))
    print(f"\nRAW: {(before.status == 'FAIL').sum()} of {len(before)} tests failed | "
          f"CLEAN: {(after.status == 'FAIL').sum()} of {len(after)} tests failed")
    print(log.to_string(index=False)); print(recon.to_string(index=False))
