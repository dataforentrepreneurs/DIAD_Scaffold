r"""
scripts/phase7/7_1_build_order_dossier_table.py

Phase 7 – Chatbot Prep (formerly 6B)
Step 1: Materialize the order_dossier view into a physical table
usable by chatbot / RAG pipelines.

Usage (from repo root):
    .\venv_dbt\Scripts\activate
    python scripts/phase7/7_1_build_order_dossier_table.py

Optional args:
    --config PATH
    --canonical-dataset
    --marts-dataset
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from google.cloud import bigquery
from google.oauth2 import service_account


# ---------- Paths & logging ----------

# This file is at: diad/scripts/phase7/7_1_build_order_dossier_table.py
# parents[0] = phase7, parents[1] = scripts, parents[2] = diad  ✅
ROOT_DIR = Path(__file__).resolve().parents[2]

DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "client_rawdata.json"

LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / "phase7_order_dossier.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


# ---------- Config helpers ----------

def load_raw_config(path: Path) -> dict:
    if not path.exists():
        logging.error("Config file not found: %s", path)
        raise SystemExit(1)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_client_config(raw: dict) -> dict:
    """
    Allow both:
      {
        "client": { ... },
        "gcp": { ... }
      }
    and:
      {
        "project_id": "...",
        "bq_location": "...",
        "gcp": { ... }
      }

    If 'client' exists, we use that as base and merge top-level 'gcp'
    into it so cfg['gcp'] is always available.
    """
    if "client" in raw and isinstance(raw["client"], dict):
        cfg = dict(raw["client"])  # shallow copy
        # If top-level gcp exists, attach it under client cfg as well
        if "gcp" in raw and "gcp" not in cfg:
            cfg["gcp"] = raw["gcp"]
        return cfg
    # No 'client' wrapper -> just use raw as-is
    return raw


def _resolve_candidate_path(value: str) -> Optional[Path]:
    """
    Try to resolve a possibly-relative path against a couple of bases:
    - ROOT_DIR (diad/)
    - ROOT_DIR / "config"
    """
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
    """
    Try to find a service account JSON path in:
      - the client config itself (cfg)
      - nested cfg["gcp"]
    using common key names, including "service_account_key_path".
    """
    candidate_keys = [
        "service_account_file",
        "service_account_path",
        "service_account_key",
        "service_account_json",
        "sa_key_path",
        "service_account_key_path",  # your current key
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


def build_bq_client(cfg: dict) -> bigquery.Client:
    """
    Build a BigQuery client using the service account from config.json.
    We REQUIRE a service account here to avoid accidentally using ADC.
    """
    project_id = cfg.get("project_id")
    if not project_id:
        logging.error("project_id is missing in client config.")
        raise SystemExit(1)

    location = cfg.get("bq_location", "asia-southeast1")

    sa_path = find_service_account_path(cfg)

    if not sa_path:
        logging.error(
            "No service account path found in client config.\n"
            "We looked for keys in both client and client['gcp'] using:\n"
            "  - service_account_file\n"
            "  - service_account_path\n"
            "  - service_account_key\n"
            "  - service_account_json\n"
            "  - sa_key_path\n"
            "  - service_account_key_path\n"
            "Example config snippet:\n"
            '{\n'
            '  "client": {\n'
            '    "project_id": "your-gcp-project-id",\n'
            '    "bq_location": "asia-southeast1",\n'
            '    "gcp": {\n'
            '      "service_account_key_path": "keys/client-service-account.json"\n'
            '    }\n'
            '  }\n'
            '}\n'
        )
        raise SystemExit(1)

    logging.info("Initializing BigQuery client with service account.")
    creds = service_account.Credentials.from_service_account_file(str(sa_path))
    client = bigquery.Client(
        project=project_id,
        credentials=creds,
        location=location,
    )
    return client


# ---------- BQ helpers ----------

def ensure_dataset(client: bigquery.Client, dataset_id: str, location: str) -> None:
    """Ensure dataset exists; create if missing."""
    full_id = f"{client.project}.{dataset_id}"
    try:
        client.get_dataset(full_id)
        logging.info("Dataset already exists: %s", full_id)
    except Exception:
        logging.info("Dataset not found, creating: %s", full_id)
        ds = bigquery.Dataset(full_id)
        ds.location = location
        client.create_dataset(ds)
        logging.info("Dataset created: %s", full_id)


def create_order_dossier_table(
    client: bigquery.Client,
    project_id: str,
    canonical_dataset: str,
    marts_dataset: str,
) -> None:

    source_table = f"{project_id}.{canonical_dataset}.order_dossier"
    target_table = f"{project_id}.{marts_dataset}.order_dossier_tbl"

    sql = f"""
    CREATE OR REPLACE TABLE `{target_table}` AS
    SELECT *
    FROM `{source_table}`;
    """

    logging.info("Creating materialized order dossier table:")
    logging.info("  Source: %s", source_table)
    logging.info("  Target: %s", target_table)
    logging.info("Running SQL:\n%s", sql)

    job = client.query(sql)
    job.result()

    logging.info("Order dossier table created/refreshed successfully: %s", target_table)


# ---------- Main ----------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 7 – Build materialized order_dossier table for chatbot."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to client config JSON (default: config/client_rawdata.json)",
    )
    parser.add_argument(
        "--canonical-dataset",
        default="ecommerce_canonical",
        help="Canonical dataset name (default: ecommerce_canonical)",
    )
    parser.add_argument(
        "--marts-dataset",
        default="ecommerce_mart",
        help="Marts dataset name (default: ecommerce_mart)",
    )

    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    raw_cfg = load_raw_config(config_path)
    cfg = normalize_client_config(raw_cfg)

    project_id = cfg.get("project_id")
    location = cfg.get("bq_location", "asia-southeast1")

    logging.info("Phase 7 – Order Dossier Materialization starting...")
    logging.info("Project ID       : %s", project_id)
    logging.info("Location         : %s", location)
    logging.info("Canonical dataset: %s", args.canonical_dataset)
    logging.info("Marts dataset    : %s", args.marts_dataset)
    logging.info("Config           : %s", config_path)

    client = build_bq_client(cfg)

    ensure_dataset(client, args.marts_dataset, location)

    create_order_dossier_table(
        client,
        project_id=project_id,
        canonical_dataset=args.canonical_dataset,
        marts_dataset=args.marts_dataset,
    )

    logging.info("Phase 7 - Order dossier materialization completed [OK]")


if __name__ == "__main__":
    main()
