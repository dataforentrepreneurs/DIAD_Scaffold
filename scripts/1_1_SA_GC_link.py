#!/usr/bin/env python3
r"""
1_1_SA_GC_link.py
Connect to GCP using service account, set ADC env, optionally activate gcloud,
and verify access to BigQuery & GCS.

Usage:
  python 1_1_SA_GC_link.py [--config path] [--no-gcloud] [--check-only]

- Reads config.json (or DIAD_CONFIG) with:
  client.project_id
  gcp.service_account_key_path
  gcp.use_gcloud (default false)
- Creates logs/setup.log
- Writes env.ps1 / env.sh
- Exits 0 on success, non-zero on failure

cd D:\DataForEntrepreneurs\diad
.\venv_dbt\Scripts\activate

"""

from __future__ import annotations
import os, sys, argparse
from pathlib import Path
from google.api_core.exceptions import GoogleAPIError

from gcp_utils import (
    load_config, setup_logger, get_bq_client, get_storage_client,
    write_env_helpers, run_gcloud_auth, get_adc_identity
)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="Path to config.json (or set DIAD_CONFIG)", default=None)
    ap.add_argument("--no-gcloud", action="store_true", help="Skip gcloud activation")
    ap.add_argument("--check-only", action="store_true", help="Only verify ADC; do not set env")
    args = ap.parse_args()

    logger = setup_logger(log_file="logs/setup.log")

    cfg = load_config(args.config)
    project_id = cfg["client"]["project_id"]
    key_path = (
        cfg.get("gcp", {}).get("service_account_key_path") or
        cfg.get("gcp", {}).get("key_file") or
        cfg.get("gcp", {}).get("key-file") or
        "keys/client-service-account.json"
    )
    use_gcloud = bool(cfg.get("gcp", {}).get("use_gcloud", False))

    if not project_id:
        logger.error("Missing client.project_id in config.")
        sys.exit(2)
    if not key_path or not Path(key_path).exists():
        logger.error(f"Service account key not found: {key_path}")
        sys.exit(3)

    key_abs = str(Path(key_path).resolve())

    if not args.check_only:
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_abs
        logger.info(f"Set GOOGLE_CLOUD_PROJECT={project_id}")
        logger.info(f"Set GOOGLE_APPLICATION_CREDENTIALS={key_abs}")

    # Optional gcloud activation
    if use_gcloud and not args.no_gcloud and not args.check_only:
        try:
            run_gcloud_auth(project_id, key_abs, logger)
        except Exception as e:
            logger.warning(f"gcloud activation failed: {e} (ADC still set for Python)")

    # Verify ADC identity
    cred_class, sa_email = get_adc_identity()
    logger.info(f"ADC credentials class: {cred_class}; SA: {sa_email or 'n/a'}")

    # Sanity check BQ + GCS
    try:
        bq = get_bq_client(project_id, key_abs)
        _ = list(bq.list_datasets())
        logger.info("BigQuery client OK (listed datasets).")
    except GoogleAPIError as e:
        logger.error(f"BigQuery access failed: {e}")
        sys.exit(4)

    try:
        gcs = get_storage_client(project_id, key_abs)
        _ = list(gcs.list_buckets(page_size=1))
        logger.info("Cloud Storage client OK (listed buckets).")
    except GoogleAPIError as e:
        logger.error(f"GCS access failed: {e}")
        sys.exit(5)

    if not args.check_only:
        write_env_helpers(project_id, key_abs, logger)

    logger.info("Environment ready.")
    logger.info("Next: python 1_2_enable_apis.py")
    sys.exit(0)

if __name__ == "__main__":
    main()
