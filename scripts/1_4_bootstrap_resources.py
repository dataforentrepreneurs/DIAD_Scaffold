#!/usr/bin/env python3
# 1_4_bootstrap_resources.py — unified bucket + all datasets + prefix "folders"
from __future__ import annotations

from google.cloud import bigquery, storage
from google.api_core.exceptions import NotFound as BqNotFound, Conflict as BqConflict
from google.cloud.exceptions import NotFound as GcsNotFound, Conflict as GcsConflict
from gcp_utils import load_config, setup_logger, get_bq_client, get_storage_client

def ensure_dataset(bq: bigquery.Client, project_id: str, dataset_name: str, location: str, logger):
    ds_fqn = f"{project_id}.{dataset_name}"
    try:
        existing = bq.get_dataset(ds_fqn)
        if existing.location and existing.location.lower() != location.lower():
            logger.warning(f"Dataset {ds_fqn} exists in {existing.location}, but required location is {location}! Recreating...")
            bq.delete_dataset(ds_fqn, delete_contents=True, not_found_ok=True)
            raise BqNotFound(f"Dataset {ds_fqn} was in wrong region")
        logger.info(f"Dataset exists: {ds_fqn} @ {existing.location}")
    except BqNotFound:
        ds = bigquery.Dataset(ds_fqn)
        ds.location = location
        try:
            bq.create_dataset(ds, exists_ok=True)
            logger.info(f"Created dataset: {ds_fqn} @ {location}")
        except BqConflict:
            logger.info(f"Dataset now exists (race): {ds_fqn}")

def ensure_bucket_with_prefixes(gcs: storage.Client, bucket_name: str, location: str, logger):
    try:
        bucket = gcs.get_bucket(bucket_name)
        logger.info(f"Bucket exists: gs://{bucket_name}")
    except GcsNotFound:
        bucket = storage.Bucket(gcs, name=bucket_name)
        bucket.location = location
        try:
            gcs.create_bucket(bucket)
            logger.info(f"Created bucket: gs://{bucket_name} @ {location}")
        except GcsConflict:
            bucket = gcs.get_bucket(bucket_name)
            logger.info(f"Bucket now exists (race): gs://{bucket_name}")

    # Lay down common "folders" (zero-byte keep files)
    prefixes = [
        "firestore/exports/.keep",
        "raw/firestore/.keep",
        "raw/firebase_auth_users/.keep",
        "raw/ecommerce/sales/.keep",
        "raw/ga4/daily/.keep",
        "raw/app/playstore/.keep",
        "raw/app/appstore/.keep",
        "processed/exports/.keep",
        "processed/dashboard_snapshots/.keep",
        "manifest/ingest_logs/.keep",
        "manifest/audit/.keep",
        "system/checkpoints/firestore/.keep"
    ]
    for key in prefixes:
        blob = bucket.blob(key)
        if not blob.exists():
            blob.upload_from_string(b"")
            logger.info(f"Created prefix marker: gs://{bucket_name}/{key}")
        else:
            logger.info(f"Prefix exists: gs://{bucket_name}/{key}")

def main():
    logger = setup_logger(log_file="logs/setup.log")
    cfg = load_config()

    pid = cfg["client"]["project_id"]
    loc = cfg["client"].get("bq_location") or "asia-southeast1"
    key = (
        cfg.get("gcp", {}).get("service_account_key_path") or
        cfg.get("gcp", {}).get("key_file") or
        cfg.get("gcp", {}).get("key-file") or
        "keys/client-service-account.json"
    )

    bq = get_bq_client(pid, key)
    gcs = get_storage_client(pid, key)

    ing = cfg.get("ingestion") or cfg.get("ingest") or {}
    unified_bucket = ing.get("bucket") or cfg.get("gcp", {}).get("unified_bucket")
    if not unified_bucket or unified_bucket == "YOUR_GCS_BUCKET_NAME":
        unified_bucket = f"{pid}-data-lake"

    ensure_bucket_with_prefixes(gcs, unified_bucket, loc, logger)

    # BigQuery datasets: raw + meta + firestore/firebase_auth + warehouse layers
    ds_raw   = cfg["ingest"]["datasets"]["raw"]
    ds_meta  = cfg["ingest"]["datasets"]["mart"]
    ds_fs    = cfg["client"]["sources"]["firestore"]["dataset"]
    ds_fa    = cfg["client"]["sources"]["firebase_auth"]["dataset"]

    # Optional warehouse layers
    wh = cfg.get("warehouse", {})
    ds_stg  = wh.get("staging_dataset", "staging")
    ds_can  = wh.get("canonical_dataset", "canonical")
    ds_mart = wh.get("marts_dataset", "marts")

    for ds in {ds_raw, ds_meta, ds_fs, ds_fa, ds_stg, ds_can, ds_mart}:
        ensure_dataset(bq, pid, ds, loc, logger)

    logger.info("Bootstrap (bucket + datasets + prefixes) complete. [OK]")

if __name__ == "__main__":
    main()