r"""
scripts/6_1_run_phase6a_dbt.py

Drive Phase 6A (staging → canonical → mart + tests) via Python,
instead of manually running dbt commands in VS Code.

Usage (from repo root):
    .\venv_dbt\Scripts\activate       # ensure dbt is installed in this venv
    python scripts/6_1_run_phase6a_dbt.py --mode full

Modes:
  - full      : seed + staging + canonical + mart + test
  - seeds     : only dbt seed
  - staging   : only staging models
  - canonical : only canonical models
  - mart     : only mart
  - test      : only dbt test
"""

import argparse
import subprocess
import sys
from pathlib import Path
import logging

# --- Paths (relative to repo root) ---

ROOT_DIR = Path(__file__).resolve().parents[1]          # /diad
DBT_PROJECT_DIR = ROOT_DIR / "dbt" / "diad_dbt"
DEFAULT_PROFILES_DIR = ROOT_DIR / "dbt" / "profiles"

# --- Logging setup ---

LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / "phase6a_dbt.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


import os

def run_cmd(cmd: list[str], cwd: Path) -> None:
    """Run a shell command and raise if it fails."""
    logging.info("Running: %s (cwd=%s)", " ".join(cmd), cwd)
    env = os.environ.copy()
    try:
        sys.path.insert(0, str(ROOT_DIR / "scripts"))
        from gcp_utils import load_config
        cfg = load_config()
        key_path = (
            cfg.get("gcp", {}).get("service_account_key_path") or
            cfg.get("gcp", {}).get("key_file") or
            cfg.get("gcp", {}).get("key-file") or
            "keys/client-service-account.json"
        )
        key_abs = ROOT_DIR / key_path
        if key_abs.exists():
            env["KEYFILE_PATH"] = str(key_abs.resolve())
            env["GOOGLE_APPLICATION_CREDENTIALS"] = str(key_abs.resolve())
        pid = cfg.get("client", {}).get("project_id")
        if pid:
            env["DIAD_PROJECT_ID"] = pid
            env["GOOGLE_CLOUD_PROJECT"] = pid
        loc = cfg.get("client", {}).get("bq_location")
        if loc:
            env["BQ_LOCATION"] = loc
    except Exception:
        pass

    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=False,
        env=env,
    )

    logging.info("----- dbt output start -----")
    logging.info(result.stdout)
    logging.info("----- dbt output end -----")

    if result.returncode != 0:
        logging.error("Command failed with return code %s", result.returncode)
        raise SystemExit(result.returncode)


def run_seeds(profiles_dir: Path) -> None:
    cmd = ["dbt", "seed", "--profiles-dir", str(profiles_dir)]
    run_cmd(cmd, DBT_PROJECT_DIR)


def run_staging(profiles_dir: Path) -> None:
    cmd = ["dbt", "run", "--select", "staging", "--profiles-dir", str(profiles_dir)]
    run_cmd(cmd, DBT_PROJECT_DIR)


def run_canonical(profiles_dir: Path) -> None:
    cmd = ["dbt", "run", "--select", "canonical", "--profiles-dir", str(profiles_dir)]
    run_cmd(cmd, DBT_PROJECT_DIR)


def run_mart(profiles_dir: Path) -> None:
    cmd = ["dbt", "run", "--select", "mart", "--profiles-dir", str(profiles_dir)]
    run_cmd(cmd, DBT_PROJECT_DIR)


def run_tests(profiles_dir: Path) -> None:
    cmd = ["dbt", "test", "--profiles-dir", str(profiles_dir)]
    run_cmd(cmd, DBT_PROJECT_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DIAD Phase 6A (dbt) via Python.")
    parser.add_argument(
        "--mode",
        choices=["full", "seeds", "staging", "canonical", "mart", "test"],
        default="full",
        help="Which part of Phase 6A to run.",
    )
    parser.add_argument(
        "--profiles-dir",
        default=str(DEFAULT_PROFILES_DIR),
        help="Path to dbt profiles directory (default: dbt/profiles).",
    )
    args = parser.parse_args()

    profiles_dir = Path(args.profiles_dir).resolve()
    if not profiles_dir.exists():
        logging.error("profiles-dir does not exist: %s", profiles_dir)
        raise SystemExit(1)

    logging.info("DIAD Phase 6A dbt runner starting...")
    logging.info("DBT project dir: %s", DBT_PROJECT_DIR)
    logging.info("Profiles dir   : %s", profiles_dir)
    logging.info("Mode           : %s", args.mode)

    try:
        if args.mode == "full":
            run_seeds(profiles_dir)
            run_staging(profiles_dir)
            run_canonical(profiles_dir)
            run_mart(profiles_dir)
            run_tests(profiles_dir)
        elif args.mode == "seeds":
            run_seeds(profiles_dir)
        elif args.mode == "staging":
            run_staging(profiles_dir)
        elif args.mode == "canonical":
            run_canonical(profiles_dir)
        elif args.mode == "mart":
            run_mart(profiles_dir)
        elif args.mode == "test":
            run_tests(profiles_dir)

        logging.info("Phase 6A (%s) completed successfully [OK]", args.mode)

    except SystemExit as e:
        # already logged; just exit
        logging.error("Phase 6A (%s) failed with exit code %s [FAILED]", args.mode, e.code)
        raise
    except Exception as e:
        logging.exception("Unexpected error in Phase 6A runner: %s", e)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
