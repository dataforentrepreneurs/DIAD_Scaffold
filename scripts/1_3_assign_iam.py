#!/usr/bin/env python3
"""
1_2_assign_iam.py
Assign minimal IAM roles to the DIAD service account in the client project.
Idempotent (merges bindings), retries on etag conflicts, supports dry-run.

Usage:
  python 1_2_assign_iam.py [--config path] [--dry-run]

Config (optional):
  "gcp": {
    "target_service_account": "diad-admin@diad-2.iam.gserviceaccount.com",
    "roles_to_assign": [
      "roles/bigquery.jobUser",
      "roles/bigquery.dataEditor",
      "roles/storage.objectAdmin",
      "roles/storage.admin",
      "roles/serviceusage.serviceUsageAdmin",
      "roles/storage.objectCreator"
    ],
    "max_iam_retries": 5
  }
"""

from __future__ import annotations
import argparse, time
from typing import List

from gcp_utils import (
    load_config, setup_logger,
    get_project_policy, set_project_policy, merge_bindings
)

DEFAULT_ROLES = [
    "roles/bigquery.jobUser",
    "roles/bigquery.dataEditor",
    "roles/storage.objectAdmin",
    "roles/datastore.viewer",
    "roles/run.admin",
    "roles/cloudscheduler.admin",
    "roles/secretmanager.admin",
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--dry-run", action="store_true", help="Show changes but do not write policy")
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
    
    target_sa = cfg.get("gcp", {}).get("target_service_account")
    if not target_sa or target_sa == "YOUR_RUNTIME_SERVICE_ACCOUNT_EMAIL":
        target_sa = (
            cfg.get("gcp", {}).get("chatbot_access_sa") or
            cfg.get("gcp", {}).get("chatbot_deployer_sa")
        )
    
    if (not target_sa or target_sa == "YOUR_RUNTIME_SERVICE_ACCOUNT_EMAIL") and Path(key_path).exists():
        try:
            with open(key_path, "r", encoding="utf-8") as f:
                sa_data = json.load(f)
                target_sa = sa_data.get("client_email")
        except Exception:
            pass

    roles: List[str] = cfg.get("gcp", {}).get("roles_to_assign", DEFAULT_ROLES)
    max_retries = int(cfg.get("gcp", {}).get("max_iam_retries", 5))

    member = f"serviceAccount:{target_sa}"
    logger.info(f"Assigning roles in {project_id} to {member} …")

    attempts = 0
    while True:
        attempts += 1
        policy = get_project_policy(project_id, key_path)
        bindings = policy.get("bindings", [])

        added = []
        for role in roles:
            bindings, changed = merge_bindings(bindings, role, member)
            if changed:
                added.append(role)

        if not added:
            logger.info("All roles already present. [OK]")
            return

        logger.info(f"Roles to add: {added}")
        if args.dry_run:
            logger.info("Dry-run: no policy written.")
            return

        policy["bindings"] = bindings
        try:
            set_project_policy(project_id, policy, key_path)
            logger.info("IAM roles assigned successfully. [OK]")
            return
        except Exception as e:
            if attempts >= max_retries:
                logger.error(f"Failed after {attempts} attempts: {e}")
                raise
            backoff = min(2 ** attempts, 10)
            logger.warning(f"IAM write race/conflict, retrying in {backoff}s … ({e})")
            time.sleep(backoff)

if __name__ == "__main__":
    main()
