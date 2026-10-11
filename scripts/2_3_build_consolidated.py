#!/usr/bin/env python3
"""
2_3_build_consolidated.py

Materialize consolidated tables from daily shards with schema alignment:

- <consolidated_dataset>.orders_consolidated
    FROM <firestore_dataset>.orders_<suffix>
    PARTITION BY DATE(_read_ts) CLUSTER BY _id

- <consolidated_dataset>.firebase_auth_users_consolidated
    FROM <firebase_auth_dataset>.firebase_auth_users_<suffix>
    PARTITION BY DATE(_read_ts) CLUSTER BY uid

Key features:
- Destination dataset defaults to "firebase_consolidated" (configurable via client.firebase_consolidated_dataset)
- Reads shard suffix format from config (client.export.shard.format, default "%Y%m%d")
- Enumerates shards by exact table names (no _TABLE_SUFFIX pitfalls)
- Aligns schemas across shards:
    • builds a superset of columns
    • missing columns => CAST(NULL AS <TYPE>)
    • type conflicts => coerced to STRING (or ARRAY<STRING> for repeated)
- Skips building a table if no shards match (won’t leave a blank table by accident)

Unified config used:
  client.project_id, client.bq_location
  client.export.shard.format                  # e.g. "%Y%m%d" or "%Y-%m-%d" (default "%Y%m%d")
  client.sources.firestore.dataset            # default "firestore_export"
  client.sources.firebase_auth.dataset        # default "firebase_auth_export"
  client.sources.firestore.consolidated_dataset        # default "firebase_consolidated"

Examples:
  python scripts/2_3_build_consolidated.py --config client_rawdata.json
  python scripts/2_3_build_consolidated.py --start-date 2025-07-01 --end-date 2025-10-25
  python scripts/2_3_build_consolidated.py --config client_rawdata.json --all-history
"""

from __future__ import annotations

import argparse
import datetime as dt
from typing import Dict, Iterable, List, Optional, Tuple

from google.cloud import bigquery
from google.api_core.exceptions import NotFound

from gcp_utils import load_config, setup_logger, get_bq_client

# -----------------------
# Utilities
# -----------------------

def getv(obj: dict, path: str, default=None):
    cur = obj
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def _parse_date_token(token: str) -> dt.date:
    t = str(token).strip().lower()
    if t in ("yesterday", "yday", "-1d"):
        return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).date()
    if t == "today":
        return dt.datetime.now(dt.timezone.utc).date()
    return dt.datetime.strptime(t, "%Y-%m-%d").date()

def resolve_single_day(cfg: dict) -> dt.date:
    val = getv(cfg, "client.run_date")
    return _parse_date_token(val) if val else (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1))

def daterange(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)

def date_to_suffix(d: dt.date, shard_format: str) -> str:
    return d.strftime(shard_format)

def ensure_dataset(bq: bigquery.Client, project: str, dataset_id: str, location: str):
    full_id = f"{project}.{dataset_id}"
    try:
        bq.get_dataset(full_id)
    except NotFound:
        ds = bigquery.Dataset(full_id)
        ds.location = location
        bq.create_dataset(ds)

# -----------------------
# Shard discovery & schema alignment
# -----------------------

def list_tables_like(bq: bigquery.Client, project: str, dataset: str, prefix: str) -> List[str]:
    """Return fully-qualified table names in dataset whose table_id starts with prefix + '_'."""
    out = []
    for t in bq.list_tables(f"{project}.{dataset}"):
        if t.table_id.startswith(prefix + "_"):
            out.append(f"`{project}.{dataset}.{t.table_id}`")
    return sorted(out)

def list_specific_shards(bq: bigquery.Client, project: str, dataset: str, base: str, suffixes: List[str]) -> List[str]:
    """Return fqtns that exist and match base_<suffix> for provided suffixes."""
    want = set(f"{base}_{sfx}" for sfx in suffixes)
    out = []
    for t in bq.list_tables(f"{project}.{dataset}"):
        if t.table_id in want:
            out.append(f"`{project}.{dataset}.{t.table_id}`")
    return sorted(out)

def fetch_schema(bq: bigquery.Client, fqtn: str) -> List[bigquery.SchemaField]:
    # fqtn like `project.dataset.table`
    table = bq.get_table(fqtn.strip("`"))
    return list(table.schema)

def normalize_field(field: bigquery.SchemaField) -> Tuple[str, str, str]:
    """Return (name, type, mode) for top-level fields only."""
    # BigQuery types are like "STRING", "INTEGER", "TIMESTAMP", "JSON", "FLOAT", "BOOL"
    return (field.name, field.field_type.upper(), field.mode.upper() if field.mode else "NULLABLE")

def combine_schema_superset(schemas: List[List[bigquery.SchemaField]]) -> Dict[str, Tuple[str, str]]:
    """
    Build a superset: name -> (type, mode).
    If a column appears with multiple types/modes, resolve to STRING (ARRAY<STRING> if repeated anywhere).
    """
    info: Dict[str, Dict[str, bool]] = {}
    modes: Dict[str, Dict[str, bool]] = {}

    for sch in schemas:
        for f in sch:
            name, t, m = normalize_field(f)
            info.setdefault(name, {})[t] = True
            modes.setdefault(name, {})[m] = True

    superset: Dict[str, Tuple[str, str]] = {}
    for name in sorted(info.keys()):
        types_present = list(info[name].keys())
        modes_present = list(modes[name].keys())

        is_repeated = "REPEATED" in modes_present
        # Resolve type conflicts → STRING
        base_type = "STRING" if len(types_present) > 1 else types_present[0]
        # JSON vs others → coerce to STRING (safer for UNION)
        if base_type == "JSON" and len(types_present) > 1:
            base_type = "STRING"

        if is_repeated:
            resolved_type = "ARRAY<STRING>" if (len(types_present) > 1 or base_type != "RECORD") else "ARRAY<" + base_type + ">"
            # if RECORD repeated, we’d need struct alignment; coerce to ARRAY<STRING> for safety
            if resolved_type.startswith("ARRAY<RECORD"):
                resolved_type = "ARRAY<STRING>"
            superset[name] = (resolved_type, "REPEATED")
        else:
            resolved_type = "STRING" if len(types_present) > 1 else base_type
            superset[name] = (resolved_type, "NULLABLE")

    return superset

def expr_for_field(fqtn: str, field_map: Dict[str, bigquery.SchemaField], target_type: str, mode: str, name: str) -> str:
    """
    Build a SELECT expression for one field `name` coming from table fqtn (or NULL if missing),
    cast to target_type. Handles arrays as ARRAY<STRING>.
    """
    exists = name in field_map
    if not exists:
        # Missing field: provide a typed NULL
        if target_type.startswith("ARRAY<"):
            return f"CAST(NULL AS {target_type}) AS `{name}`"
        return f"CAST(NULL AS {target_type}) AS `{name}`"

    src = f"`{name}`"
    src_type = field_map[name].field_type.upper()
    src_mode = (field_map[name].mode or "NULLABLE").upper()

    # If target is ARRAY<STRING>, we need to coerce arrays or scalars
    if target_type.startswith("ARRAY<"):
        # Ensure an array of strings
        if src_mode == "REPEATED":
            # ARRAY<STRING> ← ARRAY<*> : CAST each element to STRING
            return f"ARRAY(SELECT CAST(x AS STRING) FROM UNNEST({src}) AS x) AS `{name}`"
        else:
            # scalar → wrap as single-element array of STRING (or NULL if null)
            return f"CASE WHEN {src} IS NULL THEN CAST(NULL AS ARRAY<STRING>) ELSE [CAST({src} AS STRING)] END AS `{name}`"

    # Non-array targets:
    if target_type == "STRING":
        # Anything → STRING
        return f"CAST({src} AS STRING) AS `{name}`"

    if target_type == "JSON":
        # If already JSON, keep; else cast to STRING then to JSON safely (may fail if invalid)
        if src_type == "JSON":
            return f"{src} AS `{name}`"
        return f"TO_JSON(STRUCT({src})) AS `{name}`"

    # Otherwise cast to the target type directly
    return f"CAST({src} AS {target_type}) AS `{name}`"

def project_table_to_superset_sql(bq: bigquery.Client, fqtn: str, superset: Dict[str, Tuple[str, str]]) -> str:
    """Return SELECT clause that projects one table into the superset schema order."""
    schema = fetch_schema(bq, fqtn)
    fmap = {f.name: f for f in schema}
    cols = []
    for name, (typ, mode) in superset.items():
        cols.append(expr_for_field(fqtn, fmap, typ, mode, name))
    return f"SELECT {', '.join(cols)} FROM {fqtn}"

def build_union_create_sql(dst_fq: str, selects: List[str], partition_expr: str, cluster_fields: List[str]) -> str:
    cluster_clause = f"\nCLUSTER BY {', '.join(cluster_fields)}" if cluster_fields else ""
    return f"""
        CREATE OR REPLACE TABLE {dst_fq}
        PARTITION BY {partition_expr}{cluster_clause}
        AS
        {" UNION ALL ".join(selects)};
        """.strip()

# -----------------------
# Domain builders
# -----------------------

def build_consolidated_sql_for_domain(
    bq: bigquery.Client,
    project: str,
    src_ds: str,
    base_name: str,
    dst_ds: str,
    shard_format: str,
    suffixes: Optional[List[str]],
    logger,
    ) -> Optional[str]:
    # 1) find candidate shards
    if suffixes is None:  # all-history
        shards = list_tables_like(bq, project, src_ds, base=base_name)
    else:
        shards = list_specific_shards(bq, project, src_ds, base=base_name, suffixes=suffixes)

    if not shards:
        logger.warning(f"No matching shards for {base_name} — skipping.")
        return None

    # 2) build superset schema from all shard schemas
    schemas = [fetch_schema(bq, t) for t in shards]
    superset = combine_schema_superset(schemas)

    # 3) project each shard into superset
    selects = [project_table_to_superset_sql(bq, t, superset) for t in shards]

    # 4) create destination SQL
    dst = f"`{project}.{dst_ds}.{base_name.replace('firebase_auth_users','firebase_auth_users').replace('orders','orders')}_consolidated`"
    # partition by date(_read_ts); cluster by id key
    cluster_fields = ["uid"] if base_name == "firebase_auth_users" else ["_id"]
    return build_union_create_sql(dst, selects, partition_expr="DATE(_read_ts)", cluster_fields=cluster_fields)

# -----------------------
# Main
# -----------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="client_rawdata.json")
    ap.add_argument("--start-date", help="YYYY-MM-DD inclusive")
    ap.add_argument("--end-date", help="YYYY-MM-DD inclusive")
    ap.add_argument("--all-history", action="store_true", help="Union all shards present (ignores dates)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    logger = setup_logger(log_file="logs/consolidate.log")
    cfg = load_config(args.config)

    client = cfg["client"]
    project = client["project_id"]
    location = client["bq_location"]

    # Source datasets
    fs_ds = getv(client, "sources.firestore.dataset", "firestore_export")
    fa_ds = getv(client, "sources.firebase_auth.dataset", "firebase_auth_export")

    # Destination dataset (default to firebase_consolidated)
    out_ds = getv(client, "sources.firestore.consolidated_dataset", "firebase_consolidated")

    # Shard suffix format (e.g., "%Y%m%d" or "%Y-%m-%d")
    shard_format = getv(client, "export.shard.format", "%Y%m%d")

    # Resolve suffix list
    if args.all_history:
        suffixes = None  # signals “use all existing”
        logger.info("Using ALL HISTORY (union all shard tables present).")
    elif args.start_date and args.end_date:
        sd = _parse_date_token(args.start_date)
        ed = _parse_date_token(args.end_date)
        if ed < sd:
            raise SystemExit("end-date must be >= start-date")
        suffixes = [date_to_suffix(d, shard_format) for d in daterange(sd, ed)]
        logger.info(f"Using suffixes ({shard_format}): {suffixes[:3]}{' ...' if len(suffixes)>3 else ''}")
    else:
        d = resolve_single_day(cfg)
        suffixes = [date_to_suffix(d, shard_format)]
        logger.info(f"Using suffix ({shard_format}): {suffixes[0]}")

    # Client
    bq = get_bq_client(project, getv(cfg, "gcp.service_account_key_path"))

    # Ensure destination dataset
    ensure_dataset(bq, project, out_ds, location)

    # Build SQLs for both domains
    sql_orders = build_consolidated_sql_for_domain(
        bq=bq, project=project, src_ds=fs_ds, base_name="orders", dst_ds=out_ds,
        shard_format=shard_format, suffixes=suffixes, logger=logger
    )
    sql_auth = build_consolidated_sql_for_domain(
        bq=bq, project=project, src_ds=fa_ds, base_name="firebase_auth_users", dst_ds=out_ds,
        shard_format=shard_format, suffixes=suffixes, logger=logger
    )

    # Execute
    for name, sql in [("orders_consolidated", sql_orders), ("firebase_auth_users_consolidated", sql_auth)]:
        if not sql:
            continue
        if args.dry_run:
            logger.info(f"[DRY-RUN] {name} SQL:\n{sql}")
            continue
        job = bq.query(sql, location=location)
        job.result()
        logger.info(f"✓ {name} built successfully in {out_ds}.")

    logger.info("Consolidation complete. [OK]")

if __name__ == "__main__":
    main()
