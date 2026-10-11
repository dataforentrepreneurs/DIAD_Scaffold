r"""
scripts/7_run_all.py

Phase 7 Orchestrator – runs the right steps based on RAG mode.

RAG mode (from config/client_rawdata.json -> rag.mode):

  - "snapshot":
      * Phase 6A dbt run (6_1_run_dbt.py --mode full)
      * 7_1_build_order_dossier_table.py
      * 7_1b_build_customer_360_table.py
      * 7_2_export_order_dossier_json.py
      * 7_3_upsert_order_embeddings_pinecone.py

  - "direct_bq" (default):
      * Phase 6A dbt run
      * 7_1_build_order_dossier_table.py
      * 7_1b_build_customer_360_table.py
      * (skip GCS + Pinecone – APIs talk directly to BigQuery)

Usage (from repo root):
    .\venv_dbt\Scripts\activate
    python scripts/7_run_all.py

    # If Phase 6A already run:
    python scripts/7_run_all.py --skip-6a
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

# ---------- Paths & logging ----------

# This file is at: diad/scripts/7_run_all.py
# parents[0] = scripts, parents[1] = diad
ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "client_rawdata.json"

LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / "phase7_run_all.log"

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


def get_client_cfg(raw: dict) -> dict:
    return raw.get("client", {})


def get_rag_mode(raw: dict) -> str:
    rag_cfg = raw.get("rag") or {}
    mode = str(rag_cfg.get("mode", "direct_bq")).lower().strip()
    if mode not in {"snapshot", "direct_bq"}:
        logging.warning(
            "Unknown rag.mode='%s' in config. Falling back to 'direct_bq'.",
            mode,
        )
        return "direct_bq"
    return mode


# ---------- Runner helper ----------

def run_step(description: str, cmd: list[str], cwd: Path) -> None:
    logging.info("=== Running step: %s ===", description)
    logging.info("Command: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0:
        logging.error(
            "Step failed (%s) with exit code %s",
            description,
            result.returncode,
        )
        raise SystemExit(result.returncode)
    logging.info("=== Step completed: %s ===", description)


# ---------- Main orchestration ----------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 7 – Run-All Orchestrator (mode-aware)."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to client config JSON (default: config/client_rawdata.json)",
    )
    parser.add_argument(
        "--skip-6a",
        action="store_true",
        help="If set, do not run Phase 6A dbt (assume already run).",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    raw_cfg = load_raw_config(config_path)
    client_cfg = get_client_cfg(raw_cfg)
    rag_mode = get_rag_mode(raw_cfg)

    project_id = client_cfg.get("project_id", "<unknown>")
    bq_location = client_cfg.get("bq_location", "<unknown>")

    logging.info("Phase 7 – Run-All starting...")
    logging.info("Config     : %s", config_path)
    logging.info("Project ID : %s", project_id)
    logging.info("BQ location: %s", bq_location)
    logging.info("RAG mode   : %s", rag_mode)
    logging.info("Repo root  : %s", ROOT_DIR)

    # 0) Pre-flight Setup: Ensure datasets and raw e-commerce data exist
    run_step(
        "Phase 1D – Bootstrap BigQuery Resources & GCS Storage",
        [sys.executable, "scripts/1_4_bootstrap_resources.py"],
        cwd=ROOT_DIR,
    )

    run_step(
        "Phase 3.1 – Ingest E-Commerce Raw Data & Seeds",
        [sys.executable, "scripts/3_1_ingest_ecommerce.py"],
        cwd=ROOT_DIR,
    )

    # 1) Phase 6A – dbt (unless skipped)
    if not args.skip_6a:
        run_step(
            "Phase 6A – dbt run (6_1_run_dbt.py --mode full)",
            [sys.executable, "scripts/6_1_run_dbt.py", "--mode", "full"],
            cwd=ROOT_DIR,
        )
    else:
        logging.info("Skipping Phase 6A dbt run because --skip-6a was provided.")

    # 2) Phase 7 – common steps (both modes)
    run_step(
        "Phase 7.1 – Build order_dossier_tbl",
        [sys.executable, "scripts/phase7/7_1_build_order_dossier_table.py"],
        cwd=ROOT_DIR,
    )

    run_step(
        "Phase 7.1b – Build customer_360_tbl",
        [sys.executable, "scripts/phase7/7_1b_build_customer_360_table.py"],
        cwd=ROOT_DIR,
    )

    # 3) Branch based on RAG mode
    if rag_mode == "snapshot":
        logging.info("RAG mode is 'snapshot' – running GCS + Pinecone steps.")

        run_step(
            "Phase 7.2 – Export order_dossier_tbl to JSONL in GCS",
            [sys.executable, "scripts/phase7/7_2_export_order_dossier_json.py"],
            cwd=ROOT_DIR,
        )

        run_step(
            "Phase 7.3 – Upsert order embeddings into Pinecone",
            [sys.executable, "scripts/phase7/7_3_upsert_order_embeddings_pinecone.py"],
            cwd=ROOT_DIR,
        )

    else:
        logging.info(
            "RAG mode is 'direct_bq' – skipping GCS export and Pinecone upsert.\n"
            "Chatbots should query BigQuery directly for order context."
        )

    logging.info("Phase 7 - Run-All completed [OK]")


if __name__ == "__main__":
    main()
