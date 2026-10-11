"""
scripts/phase7/7_2_export_order_dossier_json.py

Currently we are not running it because RAG mode is 'direct_bq' – skipping GCS export and Pinecone upsert.
Chatbots should query BigQuery directly for order context.

Phase 7 – Chatbot Prep
Step 2: Export ecommerce_mart.order_dossier_tbl to JSONL in GCS
(one line per order) for RAG / debugging.

Usage (from repo root):
    .\venv_dbt\Scripts\activate
    python scripts/phase7/7_2_export_order_dossier_json.py --run-date 2025-12-01
"""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from google.cloud import bigquery, storage
from google.oauth2 import service_account


# ---------- Paths & logging ----------

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "client_rawdata.json"

LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / "phase7_export_json.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


# ---------- Config helpers (similar pattern) ----------

def load_raw_config(path: Path) -> dict:
    if not path.exists():
        logging.error("Config file not found: %s", path)
        raise SystemExit(1)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_client_config(raw: dict) -> dict:
    if "client" in raw and isinstance(raw["client"], dict):
        cfg = dict(raw["client"])
        if "gcp" in raw and "gcp" not in cfg:
            cfg["gcp"] = raw["gcp"]
        return cfg
    return raw


def _resolve_candidate_path(value: str) -> Optional[Path]:
    p = Path(value)
    candidates = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(ROOT_DIR / p)
        candidates.append(ROOT_DIR / "config" / p)
    for cand in candidates:
        if cand.exists():
            return cand
    return None


def find_service_account_path(cfg: dict) -> Optional[Path]:
    candidate_keys = [
        "service_account_file",
        "service_account_path",
        "service_account_key",
        "service_account_json",
        "sa_key_path",
        "service_account_key_path",
    ]
    sections = [cfg]
    gcp_cfg = cfg.get("gcp")
    if isinstance(gcp_cfg, dict):
        sections.append(gcp_cfg)

    for section in sections:
        for key in candidate_keys:
            value = section.get(key)
            if not value:
                continue
            resolved = _resolve_candidate_path(value)
            if resolved:
                logging.info("Using service account from key '%s': %s", key, resolved)
                return resolved
            else:
                logging.warning(
                    "Service account path from '%s' could not be resolved: %s",
                    key,
                    value,
                )
    return None


def build_credentials(cfg: dict):
    sa_path = find_service_account_path(cfg)
    if not sa_path:
        logging.error("No service account path found in client config.")
        raise SystemExit(1)
    logging.info("Loading service account credentials from %s", sa_path)
    return service_account.Credentials.from_service_account_file(str(sa_path))


def parse_run_date(run_date_str: Optional[str]) -> date:
    if not run_date_str:
        return date.today()
    return date.fromisoformat(run_date_str)


def resolve_bucket_and_prefix(cfg: dict) -> tuple[str, str]:
    """
    Try to find a GCS bucket and export prefix from config.

    We allow several shapes, for safety:

    {
      "bucket": "your-storage-bucket",
      "exports": { "order_dossier_prefix": "exports/order_dossier" }
    }

    or:

    {
      "gcs": { "bucket": "your-storage-bucket" },
      "exports": { "order_dossier_prefix": "exports/order_dossier" }
    }

    or similar.
    """
    # bucket
    bucket = None
    if "bucket" in cfg:
        bucket = cfg["bucket"]

    gcs_cfg = cfg.get("gcs") or cfg.get("storage") or {}
    bucket = bucket or gcs_cfg.get("bucket") or gcs_cfg.get("bucket_raw")

    if not bucket:
        logging.error("No GCS bucket found in config (bucket / gcs.bucket / storage.bucket_raw).")
        raise SystemExit(1)

    # export prefix
    exports_cfg = cfg.get("exports", {})
    order_prefix = exports_cfg.get("order_dossier_prefix", "exports/order_dossier")

    return bucket, order_prefix


# ---------- Core logic ----------

def export_order_dossier_jsonl(
    project_id: str,
    location: str,
    creds,
    bucket_name: str,
    order_export_prefix: str,
    run_date: date,
):
    bq_client = bigquery.Client(project=project_id, credentials=creds, location=location)
    storage_client = storage.Client(project=project_id, credentials=creds)

    source_table = f"{project_id}.ecommerce_mart.order_dossier_tbl"

    sql = f"""
    SELECT TO_JSON(t) AS order_json
    FROM `{source_table}` t
    """

    logging.info("Exporting order dossiers from %s", source_table)
    logging.info("SQL: %s", sql.strip())

    job = bq_client.query(sql)
    result_iter = job.result()

    # Local temp file
    tmp_dir = ROOT_DIR / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = tmp_dir / f"order_dossier_{run_date.isoformat()}.jsonl"

    count = 0
    with tmp_file.open("w", encoding="utf-8") as f:
        for row in result_iter:
            f.write(row["order_json"])
            f.write("\n")
            count += 1

    logging.info("Wrote %s orders to local file %s", count, tmp_file)

    # Upload to GCS
    bucket = storage_client.bucket(bucket_name)
    gcs_path = f"{order_export_prefix}/{run_date.isoformat()}/order_dossier.jsonl"
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(tmp_file)

    logging.info(
        "Uploaded order dossier JSONL to gs://%s/%s (rows=%s)",
        bucket_name,
        gcs_path,
        count,
    )


# ---------- Main ----------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 7 – Export order_dossier_tbl to JSONL in GCS"
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to client config JSON (default: config/client_rawdata.json)",
    )
    parser.add_argument(
        "--run-date",
        help="Run date in YYYY-MM-DD (default: today)",
        default=None,
    )

    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    raw_cfg = load_raw_config(config_path)
    cfg = normalize_client_config(raw_cfg)

    project_id = cfg.get("project_id")
    location = cfg.get("bq_location", "asia-southeast1")
    run_date = parse_run_date(args.run_date)

    logging.info("Phase 7 – Export order dossier JSON started...")
    logging.info("Project ID : %s", project_id)
    logging.info("Location   : %s", location)
    logging.info("Run date   : %s", run_date.isoformat())
    logging.info("Config     : %s", config_path)

    creds = build_credentials(cfg)
    bucket, order_prefix = resolve_bucket_and_prefix(cfg)

    export_order_dossier_jsonl(
        project_id=project_id,
        location=location,
        creds=creds,
        bucket_name=bucket,
        order_export_prefix=order_prefix,
        run_date=run_date,
    )

    logging.info("Phase 7 - Export order dossier JSON completed [OK]")


if __name__ == "__main__":
    main()
