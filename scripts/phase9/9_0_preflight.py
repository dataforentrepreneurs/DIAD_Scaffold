"""
scripts/phase9/9_0_preflight.py

Phase 9.0 Preflight (Client-side)

What it does:
- Loads config/client_rawdata.json (or --config)
- Establishes local identity for checks:
    Option A (recommended for your current workflow): use a temporary SA key file
      - sets GOOGLE_APPLICATION_CREDENTIALS so Python SDK works (BigQuery)
      - activates the same SA in gcloud (optional but helpful)
    Option B: use existing ADC (gcloud auth application-default login)
- Tests BigQuery connectivity (creates a query job => requires bigquery.jobs.create permission)
- Optionally checks Pinecone connectivity (if pinecone package installed and PINECONE_API_KEY is set)

Usage:
  python scripts/phase9/9_0_preflight.py --config config/client_rawdata.json
  python scripts/phase9/9_0_preflight.py --config config/client_rawdata.json --key-file keys/client-service-account.json

Notes:
- If you put EXACTLY ONE JSON file under keys/*.json, the script can auto-detect it.
"""

import argparse
import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
import subprocess
import shutil
from pathlib import Path

from google.cloud import bigquery

from dotenv import load_dotenv
load_dotenv(".env.local")

# -----------------------------
# Helpers
# -----------------------------

def _find_gcloud() -> str:
    """
    Find gcloud executable (Windows-safe: prefers gcloud.cmd).
    """
    # Windows typical
    gcloud = shutil.which("gcloud.cmd") or shutil.which("gcloud")
    if not gcloud:
        raise RuntimeError("gcloud not found on PATH. Install Google Cloud SDK and restart terminal.")
    return gcloud


def _run(cmd: list[str], quiet: bool = False) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(cmd)}\n{out}")
    if not quiet:
        return out.strip()
    return out.strip()


def _auto_detect_key_file() -> str | None:
    """
    Detect a single JSON key under repo_root/keys/*.json.
    If there are 0 or >1, returns None.
    """
    try:
        repo_root = Path(__file__).resolve().parents[2]  # .../scripts/phase9/ -> repo root
    except Exception:
        return None

    keys_dir = repo_root / "keys"
    if not keys_dir.exists():
        return None

    key_files = sorted([p for p in keys_dir.glob("*.json") if p.is_file()])
    if len(key_files) == 1:
        return str(key_files[0])
    return None


def enforce_identity(deployer_sa: str | None, key_file: str | None) -> None:
    """
    Establish credentials for *local* preflight.

    Preferred for your workflow:
    - Set GOOGLE_APPLICATION_CREDENTIALS to the key file so Python SDK (BigQuery) works.
    - Also activate the same SA in gcloud so gcloud calls run as that SA (helpful).

    If no key_file is provided, falls back to ADC flow (requires: gcloud auth application-default login).
    """
    gcloud = _find_gcloud()

    if key_file:
        k = Path(key_file)
        if not k.exists():
            raise RuntimeError(f"Key file not found: {key_file}")

        # This makes google-cloud-* libraries work (BigQuery client uses ADC)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(k)

        # Optional but useful: make gcloud use this SA too
        if deployer_sa:
            _run([gcloud, "auth", "activate-service-account", deployer_sa, "--key-file", str(k)])
            print("=== gcloud auth list ===")
            print(_run([gcloud, "auth", "list"]))

        print(f"✅ Using service-account key for local auth: {k}")
        return

    # No key provided — require ADC
    _run([gcloud, "auth", "application-default", "print-access-token"], quiet=True)
    print("✅ Application Default Credentials (ADC) OK (no key file provided).")


# -----------------------------
# Config helpers
# -----------------------------
def load_cfg(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# -----------------------------
# BigQuery checks
# -----------------------------
def build_bq_client(client_cfg: dict) -> bigquery.Client:
    project_id = client_cfg.get("project_id")
    location = client_cfg.get("bq_location") or client_cfg.get("location") or "asia-southeast1"
    return bigquery.Client(project=project_id, location=location)


def check_bq(bq: bigquery.Client) -> None:
    q = "SELECT 1 AS ok"
    job = bq.query(q)
    _ = list(job.result())
    # If this works, you have auth + bigquery.jobs.create + dataset access as needed.


# -----------------------------
# Pinecone check (optional)
# -----------------------------
def check_pinecone(index_name: str) -> None:
    api_key = os.getenv("PINECONE_API_KEY", "")
    if not api_key:
        print("ℹ Pinecone check skipped: PINECONE_API_KEY not set.")
        return
    try:
        from pinecone import Pinecone
    except Exception:
        print("ℹ Pinecone check skipped: pinecone package not installed.")
        return

    pc = Pinecone(api_key=api_key)
    idx = pc.Index(index_name)
    stats = idx.describe_index_stats()
    print("✅ Pinecone OK")
    print(stats)


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    
    parser = argparse.ArgumentParser()

    parser.add_argument("--config", default="config/client_rawdata.json")
    parser.add_argument("--key-file", default=None)
    parser.add_argument("--pinecone-index", default=None)
    args = parser.parse_args()

    cfg = load_cfg(args.config)
    gcp_cfg = cfg.get("gcp", {})
    client_cfg = cfg.get("client", {})

    key_file = (args.key_file or gcp_cfg.get("key-file") or "")

    project_id = client_cfg.get("project_id", "")
    bq_location = client_cfg.get("bq_location", "asia-southeast1")

    runtime_sa = gcp_cfg.get("chatbot_access_sa", "")
    key_file = gcp_cfg.get("key-file", "")

    deployer_sa = gcp_cfg.get("chatbot_deployer_sa", "")

    pinecone_index = args.pinecone_index or cfg.get("pinecone", {}).get("index_name") or "diad-docs-index"

    print("=== Phase 9.0 Preflight ===")
    print(f"Config path: {Path(args.config).resolve()}")
    print(f"Target project_id: {project_id}")
    print(f"BigQuery location: {bq_location}")
    print(f"Runtime SA (from config.gcp.chatbot_access_sa): {runtime_sa}")
    print(f"Pinecone index: {pinecone_index}")

    print("\n[0/3] Enforcing identity (key-based or ADC)...")
    
    enforce_identity(deployer_sa or None, key_file)

    print("\n[1/3] BigQuery connectivity (SELECT 1)...")
    bq = build_bq_client({"project_id": project_id, "bq_location": bq_location})
    check_bq(bq)
    print("✅ BigQuery OK (job executed)")

    print("\n[2/3] Pinecone connectivity (optional)...")
    check_pinecone(pinecone_index)

    print("\n✅ Preflight complete.")


if __name__ == "__main__":
    main()
