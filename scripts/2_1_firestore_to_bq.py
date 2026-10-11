#!/usr/bin/env python3
"""
2_1_firestore_to_bq.py

Export Firestore collections to GCS (NDJSON, optional gzip) and load into BigQuery.

Config model (unified):
  client.project_id, client.bq_location
  client.export: { bucket, compress, raw_base, shard: { by_date, format } }
  client.sources.firestore: {
      project_id, database, dataset, raw_prefix,
      collections: ["orders", ...],
      date_field: {"orders": "createdAt"},         # OPTIONAL per-collection Timestamp field for day filter
      write_disposition: "WRITE_APPEND"            # used when shard.by_date = false
  }

Legacy keys supported (fallbacks): firestore_* and ingestion.bucket/run_date.
"""

from __future__ import annotations

import argparse
import codecs
import datetime as dt
import gzip
import io
import json
import os
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

from google.cloud import firestore, storage, bigquery
from google.oauth2 import service_account
from google.api_core import exceptions
from google.api_core.exceptions import NotFound as BqNotFound

# DIAD helpers
from gcp_utils import (
    load_config,
    setup_logger,
    get_storage_client,
    get_bq_client,
)

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
    t = str(token).strip().lower()
    if t in ("yesterday", "yday", "-1d"):
        return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).date()
    if t in ("today",):
        return dt.datetime.now(dt.timezone.utc).date()
    return dt.datetime.strptime(t, "%Y-%m-%d").date()

def resolve_run_date(date_arg: Optional[str], cfg: dict, logger) -> str:
    # 1) CLI wins if provided
    if date_arg:
        d = _parse_run_date_token(date_arg).isoformat()
        logger.info(f"Resolved run_date={d} (source=CLI --date)")
        return d

    # 2) JSON client.run_date if present
    v = getv(cfg, "client.run_date")
    if v:
        d = _parse_run_date_token(v).isoformat()
        logger.info(f"Resolved run_date={d} (source=config.client.run_date)")
        return d

    # 3) DEFAULT = YESTERDAY (UTC)
    d = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat()
    logger.info(f"Resolved run_date={d} (source=default: yesterday)")
    return d


def _day_bounds(iso_date: str) -> Tuple[dt.datetime, dt.datetime]:
    d = dt.datetime.strptime(iso_date, "%Y-%m-%d").date()
    start = dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)
    end = start + dt.timedelta(days=1)
    return start, end

# -----------------------
# Firestore → JSON
# -----------------------

def _sanitize_firestore(obj):
    """Recursively convert Firestore types into JSON-serializable values.
       Also normalizes NaN/Inf to null."""
    import datetime as _dt, math, base64, decimal, uuid

    if isinstance(obj, _dt.datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=_dt.timezone.utc)
        return obj.isoformat()

    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None

    # GeoPoint duck-typing
    if hasattr(obj, "latitude") and hasattr(obj, "longitude"):
        return {"latitude": obj.latitude, "longitude": obj.longitude}

    # DocumentReference duck-typing
    if hasattr(obj, "path"):
        try:
            return obj.path
        except Exception:
            pass

    if isinstance(obj, (bytes, bytearray, memoryview)):
        return {"__bytes_b64__": base64.b64encode(bytes(obj)).decode("ascii")}

    if isinstance(obj, decimal.Decimal):
        try:
            return float(obj)
        except Exception:
            return str(obj)

    if isinstance(obj, uuid.UUID):
        return str(obj)

    if isinstance(obj, set):
        return list(obj)

    if isinstance(obj, dict):
        return {k: _sanitize_firestore(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_sanitize_firestore(v) for v in obj]

    return obj

def to_ndjson(doc_snap: firestore.DocumentSnapshot) -> str:
    data = doc_snap.to_dict() or {}
    data["_id"] = doc_snap.id
    try:
        data["_path"] = doc_snap.reference.path
    except Exception:
        data["_path"] = None
    try:
        rt = getattr(doc_snap, "read_time", None)
        data["_read_ts"] = rt.isoformat() if rt else dt.datetime.now(dt.timezone.utc).isoformat()
    except Exception:
        data["_read_ts"] = dt.datetime.now(dt.timezone.utc).isoformat()
    safe = _sanitize_firestore(data)
    return json.dumps(safe, separators=(",", ":"), ensure_ascii=False, allow_nan=False)

# -----------------------
# BigQuery helpers
# -----------------------

BASELINE_FIELDS = [
    bigquery.SchemaField("_id", "STRING"),
    bigquery.SchemaField("_path", "STRING"),
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
        autodetect=True,
        write_disposition=write_disposition,
        ignore_unknown_values=True,
        max_bad_records=5,
    )
    if dry_run:
        logger.info(f"[DRY-RUN] Would load {gcs_uri} into {table_id} ({location})")
        return
    job = bq.load_table_from_uri(gcs_uri, table_id, job_config=job_config, location=location)
    job.result()
    tbl = bq.get_table(table_id)
    logger.info(f"Loaded {tbl.num_rows} rows into {table_id}")

# -----------------------
# NDJSON validator
# -----------------------

def verify_ndjson(gcs: storage.Client, bucket_name: str, blob_name: str, logger, compress: bool, max_lines: int = 50) -> None:
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
            snippet = line[:200].decode("utf-8", errors="replace")
            raise ValueError(f"Invalid NDJSON at line {i}: {e}. Snippet: {snippet}")

# -----------------------
# Exporter (tempfile → upload)
# -----------------------

def export_collection_to_gcs(
    fs: firestore.Client,
    gcs: storage.Client,
    bucket_name: str,
    raw_prefix: str,
    collection: str,
    run_date: str,
    logger,
    compress: bool,
    date_field: Optional[str] = None,
    dry_run: bool = False,
) -> Tuple[Optional[str], int]:
    """Stream a Firestore collection (optionally day-filtered) into one NDJSON object in GCS."""
    ext = ".json.gz" if compress else ".json"
    path_prefix = f"{raw_prefix.strip('/')}/{collection}/{run_date}"
    blob_name = f"{path_prefix}/part-0000{ext}"
    uri = f"gs://{bucket_name}/{blob_name}"

    if dry_run:
        logger.info(f"[DRY-RUN] Would export {collection} to {uri}")
        return None, 0

    # Build source query
    if date_field:
        start_ts, end_ts = _day_bounds(run_date)
        source = fs.collection(collection).where(date_field, ">=", start_ts).where(date_field, "<", end_ts)
    else:
        source = fs.collection(collection)

    tmp_path = None
    count = 0
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=ext); os.close(fd)
        if compress:
            with gzip.open(tmp_path, mode="wt", encoding="utf-8", newline="\n") as gz:
                for doc in source.stream():
                    try:
                        gz.write(to_ndjson(doc)); gz.write("\n")
                        count += 1
                    except Exception as e:
                        logger.warning(f"Skip doc {getattr(doc, 'id', '?')}: {e}")
        else:
            with codecs.open(tmp_path, mode="w", encoding="utf-8") as out:
                for doc in source.stream():
                    try:
                        out.write(to_ndjson(doc)); out.write("\n")
                        count += 1
                    except Exception as e:
                        logger.warning(f"Skip doc {getattr(doc, 'id', '?')}: {e}")

        bucket = gcs.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(tmp_path, content_type=("application/gzip" if compress else "application/json"))
        logger.info(f"Uploaded {uri} ({count} docs)")
        return uri, count
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except Exception: pass

# -----------------------
# Entrypoint
# -----------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="client_rawdata.json", help="Path to DIAD config JSON")
    ap.add_argument("--date", default=None, help="Run date YYYY-MM-DD (or today/yesterday)")
    ap.add_argument("--collections", nargs="*", help="Override collections from config")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    logger = setup_logger(log_file="logs/ingest.log")
    cfg = load_config(args.config)

    client = cfg["client"]
    ingestion = cfg.get("ingestion", {})
    gcp_cfg = cfg.get("gcp", {})

    # Shared defaults (unified)
    bucket_name = getv(client, "export.bucket") or ingestion.get("bucket") or client.get("firestore_export_bucket")
    compress    = bool(getv(client, "export.compress", getv(client, "firestore_compress", False)))
    raw_base    = getv(client, "export.raw_base", "raw")
    shard_by    = bool(getv(client, "export.shard.by_date", getv(client, "firestore_shard_tables_by_date", False)))
    shard_fmt   = getv(client, "export.shard.format", client.get("firestore_shard_format", "%Y%m%d"))

    runner_project = client["project_id"]
    location = client["bq_location"]

    # Firestore source (unified with fallbacks)
    fs_src      = getv(client, "sources.firestore", {}) or {}
    fs_project  = fs_src.get("project_id") or client.get("firestore_project_id")
    if not fs_project or fs_project == "YOUR_FIREBASE_PROJECT_ID":
        fs_project = runner_project
    fs_db       = fs_src.get("database", client.get("firestore_database", "(default)"))
    dataset     = fs_src.get("dataset", client.get("firestore_export_dataset", "firestore_export"))
    raw_prefix  = fs_src.get("raw_prefix", client.get("firestore_raw_prefix", f"{raw_base}/firestore"))
    collections = args.collections or fs_src.get("collections", client.get("firestore_collections", []))
    date_field_map: Dict[str, str] = fs_src.get("date_field", {})  # optional per-collection field
    write_disp_cfg = fs_src.get("write_disposition", client.get("firestore_write_disposition", "WRITE_APPEND"))

    if not bucket_name:
        logger.error("No bucket configured. Set client.export.bucket OR ingestion.bucket OR client.firestore_export_bucket.")
        sys.exit(2)
    if not collections:
        logger.error("No Firestore 'collections' defined and none provided via --collections.")
        sys.exit(2)

    run_date = resolve_run_date(args.date, cfg, logger)
    logger.info(f"Resolved run_date={run_date}")

    # Clients
    bq = get_bq_client(runner_project, gcp_cfg.get("service_account_key_path"))
    gcs = get_storage_client(runner_project, gcp_cfg.get("service_account_key_path"))

    # Force SA creds for Firestore (avoid user ADC)
    sa_path = gcp_cfg.get("service_account_key_path")
    if not sa_path:
        logger.error("Missing gcp.service_account_key_path in config. Cannot auth to Firestore.")
        sys.exit(2)

    creds = service_account.Credentials.from_service_account_file(sa_path)
    creds = creds.with_quota_project(runner_project)
    try:
        logger.info(f"Using SA principal for Firestore: {creds.service_account_email}")
    except Exception:
        pass

    fs = firestore.Client(project=fs_project, database=fs_db, credentials=creds)

    logger.info(
        f"Starting Firestore -> GCS -> BQ | fs_project={fs_project} db={fs_db} "
        f"collections={collections} date={run_date}"
    )

    # Export and load per collection
    for coll in collections:
        date_field = date_field_map.get(coll)
        try:
            uri, count = export_collection_to_gcs(
                fs=fs,
                gcs=gcs,
                bucket_name=bucket_name,
                raw_prefix=raw_prefix,
                collection=coll,
                run_date=run_date,
                logger=logger,
                compress=compress,
                date_field=date_field,
                dry_run=args.dry_run,
            )
        except (exceptions.NotFound, exceptions.PermissionDenied) as exc:
            logger.warning(f"Firestore database or collection '{coll}' not found or accessible in project {fs_project}: {exc}. Skipping collection.")
            continue
        except Exception as exc:
            logger.error(f"Unexpected error querying Firestore collection '{coll}': {exc}. Skipping collection.")
            continue

        # Decide target table (sharded vs consolidated)
        if shard_by:
            shard_suffix = dt.datetime.strptime(run_date, "%Y-%m-%d").strftime(shard_fmt)
            table_name = f"{coll}_{shard_suffix}"
            write_disp = "WRITE_TRUNCATE"  # idempotent reruns per day
        else:
            table_name = coll
            write_disp = write_disp_cfg

        # Ensure baseline table exists
        ensure_table_exists(bq, runner_project, dataset, table_name, logger)

        if not uri or count == 0:
            logger.info(f"Skip BigQuery load for {table_name} — no documents exported.")
            continue

        # Validate NDJSON before BQ load (first 50 lines)
        blob_name = uri.replace(f"gs://{bucket_name}/", "")
        verify_ndjson(gcs, bucket_name, blob_name, logger, compress=compress, max_lines=50)

        # Load
        load_gcs_json_to_bq(
            bq=bq,
            project=runner_project,
            dataset=dataset,
            table=table_name,
            gcs_uri=uri,
            location=location,
            write_disposition=write_disp,
            logger=logger,
            dry_run=args.dry_run,
        )

    logger.info("Firestore -> GCS -> BigQuery complete. [OK]")

if __name__ == "__main__":
    main()
