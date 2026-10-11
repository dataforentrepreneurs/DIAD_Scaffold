
"""
Upload ./seed/*.csv to GCS under gs://<bucket>/<gcs_prefix>/<YYYY-MM-DD>/
"""
import json, os, pathlib, sys
from datetime import date, timedelta
from google.cloud import storage

# DIAD helpers
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from gcp_utils import get_run_date

BASE = pathlib.Path(__file__).parent
CFG = json.load(open(BASE.parent.parent / "config" / "client_rawdata.json", "r", encoding="utf-8"))
PROJECT = CFG["client"]["project_id"]
ing = CFG.get("ingestion") or CFG.get("ingest") or {}
bucket_name = (
    CFG.get("client", {}).get("export", {}).get("bucket") or
    ing.get("bucket") or
    CFG.get("gcp", {}).get("unified_bucket")
)
if not bucket_name or bucket_name == "YOUR_GCS_BUCKET_NAME":
    bucket_name = f"{PROJECT}-data-lake"

BUCKET_URI = f"gs://{bucket_name}"
PREFIX = CFG.get("ingest", {}).get("gcs_prefix", "raw/ecommerce/sales")
KEY = (
    CFG.get("gcp", {}).get("service_account_key_path") or
    CFG.get("gcp", {}).get("key_file") or
    CFG.get("gcp", {}).get("key-file") or
    "keys/client-service-account.json"
)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY
st = storage.Client(project=PROJECT)
bucket = st.bucket(bucket_name)

seed_dir = BASE / "seed"
if not seed_dir.exists():
    raise SystemExit("Seed folder not found. Run generate_seed.py first.")


run_date = get_run_date(CFG)
date_str = run_date.isoformat()
gcs_prefix = f"{PREFIX.strip('/')}/{date_str}"

for p in seed_dir.glob("*.csv"):
    blob = bucket.blob(f"{gcs_prefix}/{p.name}")
    blob.upload_from_filename(str(p))
    print("Uploaded:", blob.name)

print("GCS prefix:", f"gs://{bucket_name}/{gcs_prefix}/")
