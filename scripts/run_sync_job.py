#!/usr/bin/env python3
"""
scripts/run_sync_job.py
=======================
Unified recurring job executor for DIAD data & document pipelines.
Designed to be invoked by Cloud Scheduler, Cloud Run Jobs, or local cron.

Usage examples:
  # Daily Ecommerce sync (orders, payments, shipments -> BigQuery marts)
  python scripts/run_sync_job.py --task ecommerce

  # Weekly/Daily Google Drive incremental sync
  python scripts/run_sync_job.py --task docs --source gdrive --incremental

  # Weekly Confluence sync
  python scripts/run_sync_job.py --task docs --source confluence --incremental

  # Day 1 Initial Backfill (all data + all documents)
  python scripts/run_sync_job.py --task all --force
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "client_rawdata.json"
LOGS_DIR = REPO_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGS_DIR / "recurring_sync.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("run_sync_job")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Could not read client_rawdata.json: %s", e)
    return {}


def run_cmd(cmd: list) -> int:
    cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    logger.info("Executing: %s", cmd_str)
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), env=os.environ.copy())
    if res.returncode != 0:
        logger.error("Command exited with code %d", res.returncode)
    return res.returncode


def run_ecommerce_sync() -> int:
    logger.info("==================================================")
    logger.info("🛒 Starting Ecommerce Data Sync Pipeline")
    logger.info("==================================================")
    
    python_bin = sys.executable or "python"
    
    # 1. Ingest ecommerce raw data
    ingest_script = REPO_ROOT / "scripts" / "3_1_ingest_ecommerce.py"
    if ingest_script.exists():
        logger.info("--- Step 1: Ingest Ecommerce Raw Data ---")
        code = run_cmd([python_bin, str(ingest_script)])
        if code != 0:
            logger.warning("Ingestion step failed (or partial). Continuing to dbt models...")

    # 2. Run dbt analytical models (staging -> canonical)
    dbt_script = REPO_ROOT / "scripts" / "6_1_run_dbt.py"
    if dbt_script.exists():
        logger.info("--- Step 2: Run dbt Analytical Models ---")
        code = run_cmd([python_bin, str(dbt_script)])
        if code != 0:
            logger.error("dbt transformations failed.")
            return code

    # 3. Build Marts (order_dossier_tbl, customer_360_tbl)
    marts_script = REPO_ROOT / "scripts" / "7_run_all.py"
    if marts_script.exists():
        logger.info("--- Step 3: Build Ecommerce Marts (order_dossier_tbl) ---")
        code = run_cmd([python_bin, str(marts_script), "--skip-6a"])
        if code != 0:
            logger.error("Marts compilation failed.")
            return code

    logger.info("✅ Ecommerce data pipeline completed successfully!")
    return 0


def run_docs_sync(source: str = "all", incremental: bool = True, force: bool = False) -> int:
    logger.info("==================================================")
    logger.info("📄 Starting Document Sync Pipeline (source=%s, incremental=%s)", source, incremental)
    logger.info("==================================================")
    
    python_bin = sys.executable or "python"
    sync_script = REPO_ROOT / "scripts" / "phase8" / "8_2_sync_docs_to_pinecone.py"
    if not sync_script.exists():
        logger.error("Document sync script not found at %s", sync_script)
        return 1

    cmd = [python_bin, str(sync_script), "--config", str(CONFIG_PATH), "--source", source]
    if incremental and not force:
        cmd.append("--incremental")
    if force:
        cmd.append("--force")

    code = run_cmd(cmd)
    if code == 0:
        logger.info("✅ Document sync completed successfully for source '%s'!", source)
    return code


def main():
    parser = argparse.ArgumentParser(description="DIAD Unified Sync Job Runner")
    parser.add_argument(
        "--task",
        required=True,
        choices=["ecommerce", "docs", "all"],
        help="Pipeline task to execute",
    )
    parser.add_argument(
        "--source",
        default="all",
        choices=["all", "gdrive", "drive", "notion", "confluence"],
        help="Documentation source to filter (for --task docs)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        default=True,
        help="Only process new or modified documents",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force full processing of all records and documents",
    )

    args = parser.parse_args()

    start_time = time.time()
    logger.info("Starting DIAD Sync Job: task=%s at %s", args.task, time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()))

    exit_code = 0
    if args.task in ("ecommerce", "all"):
        exit_code = run_ecommerce_sync()
        if exit_code != 0 and args.task == "ecommerce":
            sys.exit(exit_code)

    if args.task in ("docs", "all"):
        doc_code = run_docs_sync(source=args.source, incremental=args.incremental, force=args.force)
        if doc_code != 0:
            exit_code = doc_code

    duration = time.time() - start_time
    logger.info("DIAD Sync Job finished in %.1f seconds with exit code %d", duration, exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
