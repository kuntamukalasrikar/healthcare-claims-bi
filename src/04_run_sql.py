"""Step 4 - Run every query in sql/01_kpi_analysis.sql and save each result to outputs/sql_results/."""
from pathlib import Path
import re
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "sql_results"; OUT.mkdir(parents=True, exist_ok=True)
con = sqlite3.connect(ROOT / "data" / "claims_warehouse.db")

sql = (ROOT / "sql" / "01_kpi_analysis.sql").read_text()
for name, body in re.findall(r"-- @name: (\w+)\n(.*?)(?=-- @name:|\Z)", sql, flags=re.S):
    df = pd.read_sql(body, con)
    df.to_csv(OUT / f"{name}.csv", index=False)
    print(f"\n=== {name} ===\n{df.head(12).to_string(index=False)}")
