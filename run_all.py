"""Run the full pipeline end to end: generate -> validate/cleanse -> warehouse -> SQL -> reports."""
import subprocess, sys
for step in ["01_generate_data", "02_data_quality", "03_build_warehouse", "04_run_sql", "05_build_reports"]:
    print(f"\n######## {step} ########")
    subprocess.run([sys.executable, f"src/{step}.py"], check=True)
