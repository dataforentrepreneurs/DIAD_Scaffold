#!/usr/bin/env python3
"""
1_1_enable_apis.py
Enable required Google Cloud APIs as quietly as possible (idempotent).

Usage:
  python 1_1_enable_apis.py [--config path] [--dry-run]

Config (optional):
  "gcp": {
    "enable_apis": [
      "analyticsadmin.googleapis.com",
      "bigquery.googleapis.com",
      "iam.googleapis.com",
      "cloudresourcemanager.googleapis.com",
      "firestore.googleapis.com",
      "serviceusage.googleapis.com"
    ]
  }
If not provided, a sensible default list is used.
"""

from __future__ import annotations
import argparse, time
from gcp_utils import (
    load_config, setup_logger, list_enabled_apis, enable_api
)

DEFAULT_APIS = [
    "analyticsadmin.googleapis.com",
    "bigquery.googleapis.com",
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "firestore.googleapis.com",
    "serviceusage.googleapis.com",
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "storage.googleapis.com",
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--dry-run", action="store_true", help="Show actions but do not enable")
    args = ap.parse_args()

    logger = setup_logger(log_file="logs/setup.log")
    cfg = load_config(args.config)
    project_id = cfg["client"]["project_id"]
    key_path = cfg["gcp"].get("service_account_key_path")
    apis = cfg.get("gcp", {}).get("enable_apis", DEFAULT_APIS)

    logger.info(f"Checking enabled APIs in project {project_id} …")
    already = list_enabled_apis(project_id, key_path)
    to_enable = [a for a in apis if a not in already]

    if not to_enable:
        logger.info("All required APIs already enabled. [OK]")
        return

    logger.info(f"APIs to enable ({len(to_enable)}): {to_enable}")
    if args.dry_run:
        logger.info("Dry-run: no changes made.")
        return

    for api in to_enable:
        enable_api(project_id, api, key_path, logger)
        time.sleep(0.4)

    # Recheck
    post = list_enabled_apis(project_id, key_path)
    missing = [a for a in apis if a not in post]
    if missing:
        logger.warning(f"Some APIs still not enabled (may require org policy or retry): {missing}")
    else:
        logger.info("All required APIs enabled. [OK]")

if __name__ == "__main__":
    main()
