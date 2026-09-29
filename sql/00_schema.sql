-- Star schema for the Claims BI model (SQLite dialect; ports to SQL Server / Snowflake with minor type changes)
-- Grain of fact_claims: one row per adjudicated claim.
-- Grain of fact_member_months: one row per member per enrolled month (denominator for PMPM).

DROP TABLE IF EXISTS fact_claims;
DROP TABLE IF EXISTS fact_member_months;
DROP TABLE IF EXISTS dim_member;
DROP TABLE IF EXISTS dim_provider;
DROP TABLE IF EXISTS dim_plan;
DROP TABLE IF EXISTS dim_date;

CREATE TABLE dim_plan (
    plan_id           TEXT PRIMARY KEY,
    plan_name         TEXT NOT NULL,
    line_of_business  TEXT NOT NULL,
    monthly_premium   REAL NOT NULL
);

CREATE TABLE dim_member (
    member_id              TEXT PRIMARY KEY,
    gender                 TEXT,
    birth_year             INTEGER,
    age_band               TEXT,
    state                  TEXT,
    plan_id                TEXT REFERENCES dim_plan(plan_id),
    enrollment_start       DATE,
    enrollment_end         DATE,
    chronic_condition_flag INTEGER
);

CREATE TABLE dim_provider (
    provider_id     TEXT PRIMARY KEY,
    npi             TEXT,
    provider_name   TEXT,
    specialty       TEXT,
    network_status  TEXT,
    state           TEXT
);

CREATE TABLE dim_date (
    date_key     INTEGER PRIMARY KEY,   -- yyyymmdd
    full_date    DATE NOT NULL,
    year         INTEGER,
    quarter      TEXT,
    month_num    INTEGER,
    month_name   TEXT,
    year_month   TEXT,
    is_weekend   INTEGER
);

CREATE TABLE fact_claims (
    claim_id               TEXT PRIMARY KEY,
    member_id              TEXT NOT NULL REFERENCES dim_member(member_id),
    provider_id            TEXT NOT NULL REFERENCES dim_provider(provider_id),
    plan_id                TEXT NOT NULL REFERENCES dim_plan(plan_id),
    service_date_key       INTEGER REFERENCES dim_date(date_key),
    service_date           DATE,
    received_date          DATE,
    processed_date         DATE,
    claim_type             TEXT,
    diagnosis_code         TEXT,
    billed_amount          REAL CHECK (billed_amount > 0),
    allowed_amount         REAL,
    paid_amount            REAL,
    member_responsibility  REAL,
    claim_status           TEXT CHECK (claim_status IN ('Paid','Denied','Pending')),
    denial_reason          TEXT,
    turnaround_days        INTEGER,   -- processed - received
    within_sla_flag        INTEGER    -- 1 if processed within 30 days (clean-claim SLA)
);

CREATE TABLE fact_member_months (
    member_id   TEXT REFERENCES dim_member(member_id),
    plan_id     TEXT REFERENCES dim_plan(plan_id),
    month_key   INTEGER,              -- yyyymm01 -> joins to dim_date
    year_month  TEXT,
    PRIMARY KEY (member_id, month_key)
);

CREATE INDEX ix_claims_member   ON fact_claims(member_id);
CREATE INDEX ix_claims_provider ON fact_claims(provider_id);
CREATE INDEX ix_claims_date     ON fact_claims(service_date_key);
