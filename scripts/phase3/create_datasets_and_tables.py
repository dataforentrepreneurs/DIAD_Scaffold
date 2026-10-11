
"""
Create RAW and CANONICAL datasets (if missing) and ensure canonical tables (from schema.sql).
"""
import json, os, pathlib
from google.cloud import bigquery

BASE = pathlib.Path(__file__).parent
CFG = json.load(open(BASE.parent.parent / "config" / "client_rawdata.json", "r", encoding="utf-8"))
PROJECT = CFG["client"]["project_id"]
LOCATION = CFG["client"]["bq_location"]
RAW_DS = CFG["ingest"]["datasets"]["raw"]
CAN_DS = CFG["ingest"]["datasets"]["canonical"]
KEY = (
    CFG.get("gcp", {}).get("service_account_key_path") or
    CFG.get("gcp", {}).get("key_file") or
    CFG.get("gcp", {}).get("key-file") or
    "keys/client-service-account.json"
)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY
bq = bigquery.Client(project=PROJECT, location=LOCATION)

# Create datasets if needed
for ds in (RAW_DS, CAN_DS):
    ref = bigquery.Dataset(f"{PROJECT}.{ds}")
    ref.location = LOCATION
    try:
        existing = bq.get_dataset(ref)
        if existing.location and existing.location.lower() != LOCATION.lower():
            print(f"Recreating {PROJECT}.{ds} in correct location {LOCATION} (was {existing.location})")
            bq.delete_dataset(ref, delete_contents=True, not_found_ok=True)
            raise Exception("Wrong location")
        print("Dataset exists:", f"{PROJECT}.{ds}", f"@{existing.location}")
    except Exception:
        bq.create_dataset(ref)
        print("Dataset created:", f"{PROJECT}.{ds}", f"@{LOCATION}")

# Render schema.sql and execute
schema_path = BASE / "schema.sql"
sql = schema_path.read_text(encoding="utf-8").replace("{canonical_dataset}", f"{PROJECT}.{CAN_DS}")
bq.query(sql).result()
print("Canonical tables ensured.")
