#!/usr/bin/env python3
"""
gcp_utils.py
Shared helpers for DIAD v2.0 onboarding scripts.

Features:
- Config loading from DIAD_CONFIG or ./config.json
- Unified credentials (SA key if provided, else ADC)
- Discovery service factory (no local cache)
- Native BigQuery / Storage clients
- Simple structured logger (stdout + optional file)
- Service Usage helpers (check/enable APIs)
- IAM helpers (get/set policy with retries)
- gcloud helpers (optional CLI activation)
"""

from __future__ import annotations
import os, json, sys, time, logging, subprocess, shutil, pathlib, datetime
from typing import Optional, Iterable, Tuple, Dict, Any, List

import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.cloud import bigquery, storage

import datetime

DEFAULT_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)


# ---------------------------
# Logging
# ---------------------------
def setup_logger(name: str = "diad", log_file: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger

# ---------------------------
# Config
# ---------------------------
def _resolve_config_path(path: Optional[str]) -> str:
    env_path = os.getenv("DIAD_CONFIG")
    candidate = env_path or path or "config.json"
    if os.path.isabs(candidate):
        return candidate
    if os.path.exists(candidate):
        return candidate
    here = os.path.dirname(os.path.abspath(__file__))
    fallback = os.path.join(here, candidate)
    return fallback

def load_config(path: Optional[str] = None) -> dict:
    cfg_path = _resolve_config_path(path)
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)

# ---------------------------
# Credentials & Clients
# ---------------------------
def _get_credentials(scopes=DEFAULT_SCOPES, key_path: Optional[str] = None):
    if key_path and os.path.exists(key_path):
        return service_account.Credentials.from_service_account_file(key_path, scopes=scopes)
    creds, _ = google.auth.default(scopes=list(scopes))
    return creds

def get_authenticated_service(api_name: str, api_version: str, key_path: Optional[str] = None):
    creds = _get_credentials(DEFAULT_SCOPES, key_path)
    # cache_discovery=False avoids file cache prompts
    return build(api_name, api_version, credentials=creds, cache_discovery=False)

def get_bq_client(project_id: str, key_path: Optional[str] = None) -> bigquery.Client:
    creds = _get_credentials(DEFAULT_SCOPES, key_path)
    return bigquery.Client(project=project_id, credentials=creds)

def get_storage_client(project_id: str, key_path: Optional[str] = None) -> storage.Client:
    creds = _get_credentials(DEFAULT_SCOPES, key_path)
    return storage.Client(project=project_id, credentials=creds)

def get_adc_identity() -> Tuple[str, Optional[str]]:
    """Return (cred_class, service_account_email|None)."""
    try:
        creds, proj = google.auth.default(scopes=list(DEFAULT_SCOPES))
        email = getattr(creds, "service_account_email", None)
        return (creds.__class__.__name__, email)
    except Exception as e:
        return (f"unavailable: {e}", None)

# ---------------------------
# Service Usage (APIs)
# ---------------------------
def list_enabled_apis(project_id: str, key_path: Optional[str] = None) -> set:
    svc = get_authenticated_service("serviceusage", "v1", key_path)
    enabled = set()
    req = svc.services().list(parent=f"projects/{project_id}", filter="state:ENABLED")
    while req is not None:
        resp = req.execute()
        for s in resp.get("services", []):
            enabled.add(s["name"].split("/")[-1])  # e.g. "bigquery.googleapis.com"
        req = svc.services().list_next(previous_request=req, previous_response=resp)
    return enabled

def enable_api(project_id: str, api: str, key_path: Optional[str] = None, logger: Optional[logging.Logger] = None):
    logger = logger or setup_logger()
    svc = get_authenticated_service("serviceusage", "v1", key_path)
    name = f"projects/{project_id}/services/{api}"
    try:
        op = svc.services().enable(name=name).execute()
        # Some responses are LROs; we best-effort wait a bit
        logger.info(f"Requested enable for {api}; op: {op.get('name', 'n/a')}")
        time.sleep(0.7)
    except HttpError as e:
        # If already enabled or permission issues—surface cleanly
        logger.warning(f"Enable API error for {api}: {e}")

# ---------------------------
# IAM policy helpers
# ---------------------------
def get_project_policy(project_id: str, key_path: Optional[str] = None) -> dict:
    crm = get_authenticated_service("cloudresourcemanager", "v1", key_path)
    return crm.projects().getIamPolicy(resource=project_id, body={}).execute()

def set_project_policy(project_id: str, policy: dict, key_path: Optional[str] = None) -> dict:
    crm = get_authenticated_service("cloudresourcemanager", "v1", key_path)
    return crm.projects().setIamPolicy(resource=project_id, body={"policy": policy}).execute()

def merge_bindings(bindings: List[dict], role: str, member: str) -> Tuple[List[dict], bool]:
    """Return (updated_bindings, changed?)."""
    changed = False
    rb = next((b for b in bindings if b.get("role") == role), None)
    if rb:
        members = set(rb.get("members", []))
        if member not in members:
            members.add(member)
            rb["members"] = sorted(members)
            changed = True
    else:
        bindings.append({"role": role, "members": [member]})
        changed = True
    return bindings, changed

# ---------------------------
# gcloud helpers (optional)
# ---------------------------
def find_gcloud() -> Optional[str]:
    cand = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if cand:
        return cand
    # Common Windows paths
    candidates = [
        r"C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd")
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

def run_gcloud_auth(project_id: str, key_path: str, logger: Optional[logging.Logger] = None):
    logger = logger or setup_logger()
    gcloud = find_gcloud()
    if not gcloud:
        logger.info("gcloud not found on PATH; skipping CLI activation.")
        return
    def sh(cmd: list):
        subprocess.run([gcloud] + cmd, check=True, text=True)
    logger.info("Activating service account in gcloud…")
    sh(["auth", "activate-service-account", f"--key-file={key_path}"])
    logger.info("Setting gcloud project…")
    sh(["config", "set", "project", project_id])
    logger.info("gcloud auth list:")
    subprocess.run([gcloud, "auth", "list"], check=False, text=True)

# ---------------------------
# Misc
# ---------------------------
def write_env_helpers(project_id: str, key_abs: str, logger: Optional[logging.Logger] = None):
    logger = logger or setup_logger()
    ps1 = "env.ps1"
    shf = "env.sh"
    with open(ps1, "w", encoding="utf-8") as f:
        f.write(f'$env:GOOGLE_CLOUD_PROJECT = "{project_id}"\n')
        f.write(f'$env:GOOGLE_APPLICATION_CREDENTIALS = "{key_abs}"\n')
    with open(shf, "w", encoding="utf-8") as f:
        f.write(f'export GOOGLE_CLOUD_PROJECT="{project_id}"\n')
        f.write(f'export GOOGLE_APPLICATION_CREDENTIALS="{key_abs}"\n')
    logger.info(f"Wrote helper scripts: {ps1}, {shf}")

def get_run_date(cfg) -> datetime.date:
    # A) explicit ISO date
    s = cfg.get("client", {}).get("run_date")
    if s:
        return datetime.date.fromisoformat(s)
    # B) relative offset (default: -1 = yesterday)
    offset = int(cfg.get("client", {}).get("run_date_offset_days", -1))
    return datetime.date.today() + datetime.timedelta(days=offset)