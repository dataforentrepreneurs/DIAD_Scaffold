#!/usr/bin/env python3
"""
2_2_firebase_auth_users_to_bq.py

Export Firebase Auth users to GCS (NDJSON, optional gzip) and load into BigQuery.

Unified config (preferred):
  client.project_id, client.bq_location
  client.export: { bucket, compress, raw_base, shard: { by_date, format } }
  client.sources.firebase_auth: {
      project_id,                          # Firebase/Auth project (source)
      dataset,                             # BigQuery dataset (dest)
      raw_prefix,                          # optional; default: raw_base + "/firebase_auth_users"
      table_base: "firebase_auth_users"    # final table name or shard prefix
  }

Legacy keys supported as fallback:
  client.firebase_auth_* , ingestion.bucket

Behavior:
- GCS path: gs://<bucket>/<raw_prefix>/<YYYY-MM-DD>/part-0000.json[.gz]
- BQ tables: <dataset>.firebase_auth_users or firebase_auth_users_<YYYYMMDD> (if sharded)
- Creates baseline table if missing; skips load if 0 users.
"""

from __future__ import annotations

import argparse
import codecs
import datetime as dt
import gzip
import json
import os
import sys
import tempfile
from typing import Optional, Tuple

from google.oauth2 import service_account
from google.cloud import storage, bigquery
from google.api_core import exceptions
from google.api_core.exceptions import NotFound as BqNotFound

import firebase_admin
from firebase_admin import auth, credentials as fb_credentials

# DIAD helpers
from gcp_utils import load_config, setup_logger, get_storage_client, get_bq_client


# -----------------------
# Small utilities
# -----------------------

def getv(obj: dict, path: str, default=None):
    cur = obj
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def _parse_run_date_token(token: str) -> dt.date:
    token = str(token).strip().lower()
    if token == "today":
        return dt.datetime.now(dt.timezone.utc).date()
    if token in ("yesterday", "yday", "-1d"):
        return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).date()
    return dt.datetime.strptime(token, "%Y-%m-%d").date()

def resolve_run_date(date_arg: Optional[str], cfg: dict) -> str:
    if date_arg:
        return _parse_run_date_token(date_arg).isoformat()
    val = getv(cfg, "client.run_date")
    if val:
        return _parse_run_date_token(val).isoformat()
    return dt.datetime.now(dt.timezone.utc).date().isoformat()

def verify_ndjson(gcs: storage.Client, bucket_name: str, blob_name: str, compress: bool, max_lines: int = 50) -> None:
    bucket = gcs.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    data = blob.download_as_bytes()
    if compress:
        data = gzip.decompress(data)
    checked = 0
    for i, line in enumerate(data.split(b"\n"), start=1):
        if not line:
            continue
        try:
            json.loads(line.decode("utf-8"))
            checked += 1
            if checked >= max_lines:
                break
        except Exception as e:
            snippet = line[:180].decode("utf-8", errors="replace")
            raise ValueError(f"Invalid NDJSON at line {i}: {e}. Snippet: {snippet}")


# -----------------------
# Transform record
# -----------------------

def _ts_ms_to_iso(ms) -> Optional[str]:
    if not ms:
        return None
    try:
        ms = int(ms)
        return dt.datetime.fromtimestamp(ms / 1000.0, tz=dt.timezone.utc).isoformat()
    except Exception:
        return None

def to_safe(user: auth.ExportedUserRecord) -> dict:
    """Convert Firebase Auth user record to JSON-safe dict."""
    providers = [p.provider_id for p in (user.provider_data or [])]
    return {
        "uid": user.uid,
        "email": user.email,
        "phoneNumber": user.phone_number,
        "displayName": user.display_name,
        "disabled": user.disabled,
        "emailVerified": user.email_verified,
        "createdAt": _ts_ms_to_iso(getattr(user.user_metadata, "creation_timestamp", None)),
        "lastLoginAt": _ts_ms_to_iso(getattr(user.user_metadata, "last_sign_in_timestamp", None)),
        "providerIds": providers,
        "customClaims": user.custom_claims or {},
        "_read_ts": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


# -----------------------
# GCS export
# -----------------------

def export_auth_users_to_gcs(
    fb_app: firebase_admin.App,
    gcs: storage.Client,
    bucket_name: str,
    raw_prefix: str,
    run_date: str,
    logger,
    compress: bool,
    dry_run: bool = False,
) -> Tuple[Optional[str], int]:
    ext = ".json.gz" if compress else ".json"
    path_prefix = f"{raw_prefix.strip('/')}/{run_date}"
    blob_name = f"{path_prefix}/part-0000{ext}"
    uri = f"gs://{bucket_name}/{blob_name}"

    if dry_run:
        logger.info(f"[DRY-RUN] Would export Firebase Auth users to {uri}")
        return None, 0

    tmp_path = None
    count = 0
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=ext)
        os.close(fd)

        if compress:
            with gzip.open(tmp_path, mode="wt", encoding="utf-8", newline="\n") as out:
                page = auth.list_users(app=fb_app)
                while True:
                    for u in page.users:
                        out.write(json.dumps(to_safe(u), separators=(",", ":"), ensure_ascii=False))
                        out.write("\n")
                        count += 1
                    if page.next_page_token:
                        page = auth.list_users(page_token=page.next_page_token, app=fb_app)
                    else:
                        break
        else:
            with codecs.open(tmp_path, mode="w", encoding="utf-8") as out:
                page = auth.list_users(app=fb_app)
                while True:
                    for u in page.users:
                        out.write(json.dumps(to_safe(u), separators=(",", ":"), ensure_ascii=False))
                        out.write("\n")
                        count += 1
                    if page.next_page_token:
                        page = auth.list_users(page_token=page.next_page_token, app=fb_app)
                    else:
                        break

        bucket = gcs.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(tmp_path, content_type=("application/gzip" if compress else "application/json"))
        logger.info(f"Uploaded {uri} ({count} users)")
        return uri, count
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


# -----------------------
# BigQuery
# -----------------------

BASELINE_FIELDS = [
    bigquery.SchemaField("uid", "STRING"),
    bigquery.SchemaField("email", "STRING"),
    bigquery.SchemaField("phoneNumber", "STRING"),
    bigquery.SchemaField("displayName", "STRING"),
    bigquery.SchemaField("disabled", "BOOL"),
    bigquery.SchemaField("emailVerified", "BOOL"),
    bigquery.SchemaField("createdAt", "TIMESTAMP"),
    bigquery.SchemaField("lastLoginAt", "TIMESTAMP"),
    bigquery.SchemaField("providerIds", "STRING", mode="REPEATED"),
    bigquery.SchemaField("customClaims", "JSON"),
    bigquery.SchemaField("_read_ts", "TIMESTAMP"),
]

def ensure_table_exists(bq: bigquery.Client, project: str, dataset: str, table: str, logger) -> None:
    table_id = f"{project}.{dataset}.{table}"
    try:
        bq.get_table(table_id)
        return
    except BqNotFound:
        tbl = bigquery.Table(table_id, schema=BASELINE_FIELDS)
        bq.create_table(tbl)
        logger.info(f"Created baseline table: {table_id}")

def load_gcs_json_to_bq(
    bq: bigquery.Client,
    project: str,
    dataset: str,
    table: str,
    gcs_uri: str,
    location: str,
    write_disposition: str,
    logger,
    dry_run: bool = False,
):
    table_id = f"{project}.{dataset}.{table}"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        autodetect=False,
        schema=BASELINE_FIELDS,
        write_disposition=write_disposition,
        ignore_unknown_values=True,
        max_bad_records=5,
    )
    if dry_run:
        logger.info(f"[DRY-RUN] Would load {gcs_uri} into {table_id} ({location})")
        return
    job = bq.load_table_from_uri(gcs_uri, table_id, job_config=job_config, location=location)
    job.result()
    logger.info(f"Loaded into {table_id}")


# -----------------------
# Entrypoint
# -----------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="client_rawdata.json", help="Path to DIAD config JSON")
    ap.add_argument("--date", default=None, help="Run date YYYY-MM-DD (or today/yesterday)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    logger = setup_logger(log_file="logs/ingest.log")
    cfg = load_config(args.config)

    client = cfg["client"]
    ingestion = cfg.get("ingestion", {})
    gcp_cfg = cfg.get("gcp", {})

    # Shared defaults (unified)
    bucket_name = getv(client, "export.bucket") or ingestion.get("bucket") or client.get("firestore_export_bucket")
    compress    = bool(getv(client, "export.compress", client.get("firebase_auth_compress", False)))
    raw_base    = getv(client, "export.raw_base", "raw")
    shard_by    = bool(getv(client, "export.shard.by_date", client.get("firebase_auth_shard_tables_by_date", True)))
    shard_fmt   = getv(client, "export.shard.format", client.get("firebase_auth_shard_format", "%Y%m%d"))

    runner_project = client["project_id"]
    location = client["bq_location"]

    # Firebase Auth source (unified with fallbacks)
    fa_src       = getv(client, "sources.firebase_auth", {}) or {}
    auth_project = fa_src.get("project_id") or client.get("firebase_auth_project_id")
    if not auth_project or auth_project == "YOUR_FIREBASE_PROJECT_ID":
        auth_project = runner_project
    dataset      = fa_src.get("dataset", client.get("firebase_auth_export_dataset", "firebase_auth_export"))
    raw_prefix   = fa_src.get("raw_prefix", client.get("firebase_auth_raw_prefix", f"{raw_base}/firebase_auth_users"))
    table_base   = fa_src.get("table_base", "firebase_auth_users")

    if not bucket_name:
        logger.error("No bucket configured. Set client.export.bucket OR ingestion.bucket OR client.firestore_export_bucket.")
        sys.exit(2)

    run_date = resolve_run_date(args.date, cfg)
    shard_suffix = dt.datetime.strptime(run_date, "%Y-%m-%d").strftime(shard_fmt) if shard_by else ""
    logger.info(f"Resolved run_date={run_date}" + (f" (shard={shard_suffix})" if shard_suffix else ""))

    # Clients
    bq = get_bq_client(runner_project, gcp_cfg.get("service_account_key_path"))
    gcs = get_storage_client(runner_project, gcp_cfg.get("service_account_key_path"))

    sa_path = gcp_cfg.get("service_account_key_path")
    if not sa_path:
        logger.error("Missing gcp.service_account_key_path in config.")
        sys.exit(2)

    # Initialize Firebase Admin against AUTH project using the SA key
    try:
        creds = fb_credentials.Certificate(sa_path)
        fb_app = firebase_admin.initialize_app(creds, {"projectId": auth_project}, name="firebase-auth-export-app")

        # Export to GCS
        uri, count = export_auth_users_to_gcs(
            fb_app=fb_app,
            gcs=gcs,
            bucket_name=bucket_name,
            raw_prefix=raw_prefix,
            run_date=run_date,
            logger=logger,
            compress=compress,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        logger.warning(f"Firebase Auth users not found or accessible in project {auth_project}: {exc}. Skipping Firebase Auth ingestion.")
        return

    # Decide table and write mode
    table = f"{table_base}_{shard_suffix}" if shard_by else table_base
    write_disp = "WRITE_TRUNCATE" if shard_by else "WRITE_APPEND"

    # Ensure table exists (baseline)
    ensure_table_exists(bq, runner_project, dataset, table, logger)

    if not uri or count == 0:
        logger.info(f"Skip BigQuery load for {table} — no users exported.")
        return

    # Validate NDJSON before BQ load
    blob_name = uri.replace(f"gs://{bucket_name}/", "")
    verify_ndjson(gcs, bucket_name, blob_name, compress=compress, max_lines=50)

    # Load to BigQuery
    load_gcs_json_to_bq(
        bq=bq,
        project=runner_project,
        dataset=dataset,
        table=table,
        gcs_uri=uri,
        location=location,
        write_disposition=write_disp,
        logger=logger,
        dry_run=args.dry_run,
    )

    logger.info("Firebase Auth users -> GCS -> BigQuery complete. [OK]")


if __name__ == "__main__":
    main()
