"""
Step 1 - Generate a SYNTHETIC US healthcare claims dataset (no real patient data).

Simulates what a payer (health insurer) source system would hand to a BI team:
members, plans, providers and 24 months of claims (Jan 2024 - Dec 2025).

Real-world data is messy, so this script deliberately injects data-quality
defects into the raw extract (duplicates, orphan keys, bad dates, invalid
amounts, inconsistent codes). Step 2 has to catch them.
"""
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED)
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

N_MEMBERS, N_PROVIDERS, N_CLAIMS = 8_000, 400, 60_000
START, END = pd.Timestamp("2024-01-01"), pd.Timestamp("2025-12-31")
STATES = ["TX", "FL", "CA", "NY", "OH", "GA", "AZ", "MN"]

# ---------------------------------------------------------------- plans
plans = pd.DataFrame({
    "plan_id": ["P01", "P02", "P03", "P04", "P05"],
    "plan_name": ["Choice Plus PPO", "Select HMO", "Medicare Advantage Gold",
                  "Medicare Advantage Silver", "Community Medicaid"],
    "line_of_business": ["Commercial", "Commercial", "Medicare Advantage",
                         "Medicare Advantage", "Medicaid"],
    "monthly_premium": [620, 480, 1150, 980, 540],
})

# ---------------------------------------------------------------- members
plan_ids = rng.choice(plans.plan_id, N_MEMBERS, p=[.30, .25, .15, .12, .18])
is_mapd = np.isin(plan_ids, ["P03", "P04"])
age = np.where(is_mapd, rng.integers(65, 90, N_MEMBERS), rng.integers(0, 65, N_MEMBERS))
enroll_start = START + pd.to_timedelta(
    np.where(rng.random(N_MEMBERS) < .7, 0, rng.integers(0, 540, N_MEMBERS)), unit="D")
enroll_end = pd.Series(pd.NaT, index=range(N_MEMBERS))
churn = rng.random(N_MEMBERS) < .15
enroll_end[churn] = enroll_start[churn] + pd.to_timedelta(rng.integers(90, 500, churn.sum()), unit="D")
enroll_end = enroll_end.where(enroll_end <= END, pd.NaT)

members = pd.DataFrame({
    "member_id": [f"M{i:06d}" for i in range(1, N_MEMBERS + 1)],
    "gender": rng.choice(["F", "M"], N_MEMBERS),
    "birth_year": 2025 - age,
    "state": rng.choice(STATES, N_MEMBERS, p=[.2, .18, .15, .12, .1, .1, .08, .07]),
    "plan_id": plan_ids,
    "enrollment_start": enroll_start.date,
    "enrollment_end": pd.to_datetime(enroll_end).dt.date,
    "chronic_condition_flag": (rng.random(N_MEMBERS) < np.where(age >= 65, .45, .15)).astype(int),
})

# ---------------------------------------------------------------- providers
SPECIALTIES = {  # specialty: (weight, avg billed $, claim_type mix)
    "Primary Care":        (.30,   180, "Professional"),
    "Pediatrics":          (.08,   160, "Professional"),
    "Cardiology":          (.08,  1400, "Outpatient"),
    "Orthopedics":         (.08,  2100, "Outpatient"),
    "Oncology":            (.05,  4800, "Outpatient"),
    "Radiology":           (.10,   650, "Outpatient"),
    "Emergency Medicine":  (.09,  1900, "Outpatient"),
    "General Hospital":    (.07, 14500, "Inpatient"),
    "Behavioral Health":   (.08,   210, "Professional"),
    "Pharmacy":            (.07,   120, "Pharmacy"),
}
spec_names = list(SPECIALTIES)
spec = rng.choice(spec_names, N_PROVIDERS, p=[v[0] for v in SPECIALTIES.values()])
prefix = ["Lakeside", "Summit", "Riverbend", "Oak Valley", "Northgate", "Harbor", "Pinecrest",
          "Meadowbrook", "Cedar Ridge", "Silverline", "Brookfield", "Westfield"]
suffix = {"Primary Care": "Family Clinic", "Pediatrics": "Children's Clinic", "Cardiology": "Heart Center",
          "Orthopedics": "Ortho & Spine", "Oncology": "Cancer Institute", "Radiology": "Imaging",
          "Emergency Medicine": "Emergency Care", "General Hospital": "Medical Center",
          "Behavioral Health": "Wellness Group", "Pharmacy": "Pharmacy"}
providers = pd.DataFrame({
    "provider_id": [f"PR{i:04d}" for i in range(1, N_PROVIDERS + 1)],
    "npi": rng.integers(1_000_000_000, 1_999_999_999, N_PROVIDERS).astype(str),
    "provider_name": [f"{rng.choice(prefix)} {suffix[s]} #{i}" for i, s in enumerate(spec, 1)],
    "specialty": spec,
    "network_status": rng.choice(["In-Network", "Out-of-Network"], N_PROVIDERS, p=[.82, .18]),
    "state": rng.choice(STATES, N_PROVIDERS),
})

# ---------------------------------------------------------------- claims
# members with chronic conditions / older members use more care
m_weight = 1 + members.chronic_condition_flag * 2.2 + (members.birth_year <= 1960) * 1.0
m_idx = rng.choice(N_MEMBERS, N_CLAIMS, p=m_weight / m_weight.sum())
p_idx = rng.integers(0, N_PROVIDERS, N_CLAIMS)
cm, cp = members.iloc[m_idx].reset_index(drop=True), providers.iloc[p_idx].reset_index(drop=True)

# service date inside enrollment window, with winter seasonality
days_total = (END - START).days
svc = []
for s, e in zip(pd.to_datetime(cm.enrollment_start), pd.to_datetime(cm.enrollment_end)):
    e = END if pd.isna(e) else e
    svc.append(s + pd.Timedelta(days=int(rng.integers(0, max((e - s).days, 1)))))
svc = pd.Series(svc)
winter = svc.dt.month.isin([1, 2, 12])
# resample ~12% of non-winter claims into winter months (flu season uplift)
shift = (~winter) & (rng.random(N_CLAIMS) < .12)
svc[shift] = svc[shift].apply(lambda d: d.replace(month=int(rng.choice([1, 2, 12])), day=min(d.day, 28)))
svc = svc.clip(upper=END)

avg_billed = cp.specialty.map({k: v[1] for k, v in SPECIALTIES.items()})
billed = np.round(avg_billed * rng.lognormal(0, .55, N_CLAIMS), 2)
# a small set of catastrophic claims (high-cost claimants)
cat = rng.random(N_CLAIMS) < .004
billed[cat] = np.round(billed[cat] * rng.uniform(8, 20, cat.sum()), 2)

oon = cp.network_status.eq("Out-of-Network").to_numpy()
allowed_ratio = np.where(oon, rng.uniform(.35, .55, N_CLAIMS), rng.uniform(.55, .75, N_CLAIMS))
allowed = np.round(billed * allowed_ratio, 2)

# denial probability: higher out-of-network, higher for high-cost specialties (prior auth)
p_deny = .06 + oon * .13 + cp.specialty.isin(["Orthopedics", "Oncology", "Radiology"]).to_numpy() * .06
status = np.where(rng.random(N_CLAIMS) < p_deny, "Denied",
                  np.where(svc > END - pd.Timedelta(days=20), "Pending", "Paid"))
reasons = ["Missing prior authorization", "Out-of-network provider", "Duplicate claim submission",
           "Service not covered", "Missing/invalid information", "Timely filing limit exceeded"]
denial_reason = np.where(status == "Denied", None, None).astype(object)
for i in np.where(status == "Denied")[0]:
    if oon[i] and rng.random() < .45:
        denial_reason[i] = "Out-of-network provider"
    elif cp.specialty[i] in ("Orthopedics", "Oncology", "Radiology") and rng.random() < .5:
        denial_reason[i] = "Missing prior authorization"
    else:
        denial_reason[i] = rng.choice(reasons, p=[.2, .05, .2, .2, .25, .1])

member_share = np.round(allowed * np.where(cm.plan_id.eq("P05"), .02, rng.uniform(.10, .25, N_CLAIMS)), 2)
paid = np.where(status == "Paid", np.round(allowed - member_share, 2), 0.0)

received = svc + pd.to_timedelta(rng.integers(1, 30, N_CLAIMS), unit="D")
tat = rng.gamma(2.2, 5, N_CLAIMS) + np.where(cp.specialty.eq("General Hospital"), 12, 0) + np.where(status == "Denied", 6, 0)
processed = received + pd.to_timedelta(np.round(tat).astype(int), unit="D")
processed = pd.Series(processed).where(status != "Pending", pd.NaT)

DX = {"Primary Care": ["Z00.00", "I10", "E11.9", "J06.9"], "Pediatrics": ["Z00.129", "J06.9", "H66.90"],
      "Cardiology": ["I25.10", "I48.91", "I50.9"], "Orthopedics": ["M17.11", "M54.5", "S83.511A"],
      "Oncology": ["C50.911", "C34.90", "C61"], "Radiology": ["R91.8", "M54.5", "R10.9"],
      "Emergency Medicine": ["R07.9", "S09.90XA", "R10.9"], "General Hospital": ["I21.4", "J18.9", "A41.9", "I50.9"],
      "Behavioral Health": ["F32.9", "F41.1", "F43.10"], "Pharmacy": ["E11.9", "I10", "E78.5"]}
dx = [rng.choice(DX[s]) for s in cp.specialty]

claims = pd.DataFrame({
    "claim_id": [f"CLM{i:08d}" for i in range(1, N_CLAIMS + 1)],
    "member_id": cm.member_id, "provider_id": cp.provider_id,
    "claim_type": cp.specialty.map({k: v[2] for k, v in SPECIALTIES.items()}),
    "diagnosis_code": dx,
    "service_date": svc.dt.date, "received_date": received.dt.date,
    "processed_date": pd.to_datetime(processed).dt.date,
    "billed_amount": billed, "allowed_amount": allowed, "paid_amount": paid,
    "member_responsibility": np.where(status == "Denied", 0, member_share),
    "claim_status": status, "denial_reason": denial_reason,
})

# ---------------------------------------------------------------- inject DQ defects
def pick(frac):
    return rng.choice(claims.index, int(len(claims) * frac), replace=False)

dup = claims.loc[pick(.012)]                                               # exact duplicates
claims.loc[pick(.004), "provider_id"] = None                               # missing provider
claims.loc[pick(.003), "member_id"] = [f"M9{i:05d}" for i in range(int(len(claims) * .003))]  # orphan members
i = pick(.003); claims.loc[i, "billed_amount"] *= -1                      # negative billed
i = pick(.003); claims.loc[i, "paid_amount"] = claims.loc[i, "billed_amount"].abs() * 1.3  # paid > billed
i = pick(.004); claims.loc[i, "processed_date"] = (pd.to_datetime(claims.loc[i, "received_date"]) - pd.Timedelta(days=5)).dt.date
i = pick(.001); claims.loc[i, "service_date"] = pd.Timestamp("2027-03-15").date()  # future date
i = pick(.003); claims.loc[i, "diagnosis_code"] = ["999", "UNKNOWN", "N/A"] * (len(i) // 3) + ["999"] * (len(i) % 3)
i = pick(.02);  claims.loc[i, "claim_status"] = claims.loc[i, "claim_status"].str.upper() + " "  # inconsistent casing
den = claims.index[claims.claim_status.eq("Denied")]
i = rng.choice(den, 40, replace=False); claims.loc[i, "paid_amount"] = 125.00  # denied but paid

claims = pd.concat([claims, dup]).sample(frac=1, random_state=SEED).reset_index(drop=True)

plans.to_csv(RAW / "plans.csv", index=False)
members.to_csv(RAW / "members.csv", index=False)
providers.to_csv(RAW / "providers.csv", index=False)
claims.to_csv(RAW / "claims_raw.csv", index=False)
print(f"raw extract written: {len(members):,} members | {len(providers):,} providers | {len(claims):,} claim rows")
