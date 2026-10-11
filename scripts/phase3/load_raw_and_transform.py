
"""
Load CSVs from GCS into RAW, then insert into CANONICAL.
"""
import json, os, pathlib, datetime, sys
from google.cloud import bigquery

# DIAD helpers
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from gcp_utils import get_run_date

BASE = pathlib.Path(__file__).parent
CFG = json.load(open(BASE.parent.parent / "config" / "client_rawdata.json", "r", encoding="utf-8"))
PROJECT = CFG["client"]["project_id"]
LOCATION = CFG["client"]["bq_location"]
RAW_DS = CFG["ingest"]["datasets"]["raw"]
CAN_DS = CFG["ingest"]["datasets"]["canonical"]
ing = CFG.get("ingestion") or CFG.get("ingest") or {}
bucket_name = (
    CFG.get("client", {}).get("export", {}).get("bucket") or
    ing.get("bucket") or
    CFG.get("gcp", {}).get("unified_bucket")
)
if not bucket_name or bucket_name == "YOUR_GCS_BUCKET_NAME":
    bucket_name = f"{PROJECT}-data-lake"

BUCKET_URI = f"gs://{bucket_name}"
PREFIX = CFG.get("ingest", {}).get("gcs_prefix", "raw/ecommerce/sales")
KEY = (
    CFG.get("gcp", {}).get("service_account_key_path") or
    CFG.get("gcp", {}).get("key_file") or
    CFG.get("gcp", {}).get("key-file") or
    "keys/client-service-account.json"
)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY
bq = bigquery.Client(project=PROJECT, location=LOCATION)

run_date = get_run_date(CFG)
date_str = run_date.isoformat()
gcs_uri_prefix = f"{BUCKET_URI.rstrip('/')}/{PREFIX.strip('/')}/{date_str}"

files = ["dim_customer","dim_product","warehouse","sales_order_header","sales_order_line","payment","refund","shipment","shipment_item","inventory_snapshot_daily"]

# Load each to RAW using autodetect
for t in files:
    uri = f"{gcs_uri_prefix}/{t}.csv"
    dest = f"{PROJECT}.{RAW_DS}.{t}"
    job_config = bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.CSV, skip_leading_rows=1, autodetect=True, write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)
    print("Loading", uri, "->", dest)
    bq.load_table_from_uri(uri, dest, job_config=job_config).result()

# Truncate canonical (MVP idempotency)
for t in files:
    bq.query(f"TRUNCATE TABLE `{PROJECT}.{CAN_DS}.{t}`").result()

def run(sql): bq.query(sql).result()

# Inserts (typed casts + SAFE_CAST for nullable timestamps)
run(f"""
INSERT INTO `{PROJECT}.{CAN_DS}.dim_customer`
SELECT 
  CAST(customer_sk AS INT64),
  customer_id_bk,
  email,
  phone,
  full_name,
  first_name,
  last_name,
  CAST(marketing_opt_in AS BOOL),
  CAST(lifetime_value AS NUMERIC),
  TIMESTAMP(effective_start_at),
  SAFE_CAST(NULLIF(effective_end_at,'') AS TIMESTAMP),
  CAST(is_current AS BOOL),
  source_system,
  TIMESTAMP(created_at),
  TIMESTAMP(updated_at),
  CAST(is_deleted AS BOOL)
FROM `{PROJECT}.{RAW_DS}.dim_customer`
""")

run(f"""
INSERT INTO `{PROJECT}.{CAN_DS}.dim_product`
SELECT 
  CAST(product_sk AS INT64),
  product_id_bk,
  sku,
  parent_sku,
  product_name,
  brand,
  category_path,
  attributes_json,
  uom,
  status,
  TIMESTAMP(effective_start_at),
  SAFE_CAST(NULLIF(effective_end_at,'') AS TIMESTAMP),
  CAST(is_current AS BOOL),
  source_system,
  TIMESTAMP(created_at),
  TIMESTAMP(updated_at),
  CAST(is_deleted AS BOOL)
FROM `{PROJECT}.{RAW_DS}.dim_product`
""")

run(f"""
INSERT INTO `{PROJECT}.{CAN_DS}.warehouse`
SELECT 
  CAST(warehouse_sk AS INT64),
  warehouse_code,
  name,
  address_json,
  timezone,
  TIMESTAMP(created_at),
  TIMESTAMP(updated_at)
FROM `{PROJECT}.{RAW_DS}.warehouse`
""")

run(f"""
INSERT INTO `{PROJECT}.{CAN_DS}.sales_order_header`
SELECT 
  CAST(order_sk AS INT64),
  order_number,
  CAST(customer_sk AS INT64),
  order_status,
  order_channel,
  order_currency,
  TIMESTAMP(order_datetime),
  CAST(subtotal_amount AS NUMERIC),
  CAST(discount_amount AS NUMERIC),
  CAST(tax_amount AS NUMERIC),
  CAST(shipping_amount AS NUMERIC),
  CAST(total_amount AS NUMERIC),
  SAFE_CAST(NULLIF(billing_address_sk,'') AS INT64),
  SAFE_CAST(NULLIF(shipping_address_sk,'') AS INT64),
  source_system,
  TIMESTAMP(created_at),
  TIMESTAMP(updated_at)
FROM `{PROJECT}.{RAW_DS}.sales_order_header`
""")

run(f"""
INSERT INTO `{PROJECT}.{CAN_DS}.sales_order_line`
SELECT 
  CAST(order_line_sk AS INT64),
  CAST(order_sk AS INT64),
  CAST(product_sk AS INT64),
  CAST(line_number AS INT64),
  CAST(quantity_ordered AS NUMERIC),
  CAST(unit_price AS NUMERIC),
  CAST(discount_amount AS NUMERIC),
  CAST(tax_amount AS NUMERIC),
  CAST(total_line_amount AS NUMERIC),
  fulfillment_status,
  TIMESTAMP(created_at),
  TIMESTAMP(updated_at)
FROM `{PROJECT}.{RAW_DS}.sales_order_line`
""")

run(f"""
INSERT INTO `{PROJECT}.{CAN_DS}.payment`
SELECT 
  CAST(payment_sk AS INT64),
  CAST(order_sk AS INT64),
  payment_method,
  provider,
  transaction_id,
  CAST(payment_amount AS NUMERIC),
  TIMESTAMP(captured_at),
  status,
  TIMESTAMP(created_at),
  TIMESTAMP(updated_at)
FROM `{PROJECT}.{RAW_DS}.payment`
""")

run(f"""
INSERT INTO `{PROJECT}.{CAN_DS}.refund`
SELECT 
  CAST(refund_sk AS INT64),
  CAST(order_sk AS INT64),
  CAST(payment_sk AS INT64),
  CAST(refund_amount AS NUMERIC),
  refund_reason,
  TIMESTAMP(refunded_at),
  TIMESTAMP(created_at),
  TIMESTAMP(updated_at)
FROM `{PROJECT}.{RAW_DS}.refund`
""")

run(f"""
INSERT INTO `{PROJECT}.{CAN_DS}.shipment`
SELECT 
  CAST(shipment_sk AS INT64),
  CAST(order_sk AS INT64),
  CAST(warehouse_sk AS INT64),
  carrier,
  service_level,
  tracking_number,
  TIMESTAMP(shipped_at),
  TIMESTAMP(delivered_at),
  status,
  TIMESTAMP(created_at),
  TIMESTAMP(updated_at)
FROM `{PROJECT}.{RAW_DS}.shipment`
""")

run(f"""
INSERT INTO `{PROJECT}.{CAN_DS}.shipment_item`
SELECT 
  CAST(shipment_item_sk AS INT64),
  CAST(shipment_sk AS INT64),
  CAST(order_line_sk AS INT64),
  CAST(product_sk AS INT64),
  CAST(quantity_shipped AS NUMERIC),
  TIMESTAMP(created_at),
  TIMESTAMP(updated_at)
FROM `{PROJECT}.{RAW_DS}.shipment_item`
""")

run(f"""
INSERT INTO `{PROJECT}.{CAN_DS}.inventory_snapshot_daily`
SELECT 
  DATE(snapshot_date),
  CAST(product_sk AS INT64),
  CAST(warehouse_sk AS INT64),
  CAST(on_hand_qty AS NUMERIC),
  CAST(allocated_qty AS NUMERIC),
  CAST(available_qty AS NUMERIC)
FROM `{PROJECT}.{RAW_DS}.inventory_snapshot_daily`
""")

print("RAW -> CANONICAL load complete.")
