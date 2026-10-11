-- Phase 3 Canonical Schema
CREATE SCHEMA IF NOT EXISTS `{canonical_dataset}`;

CREATE OR REPLACE TABLE `{canonical_dataset}.dim_product` (
  product_sk INT64,
  product_id_bk STRING,
  sku STRING,
  parent_sku STRING,
  product_name STRING,
  brand STRING,
  category_path STRING,
  attributes_json STRING,
  uom STRING,
  status STRING,
  effective_start_at TIMESTAMP,
  effective_end_at TIMESTAMP,
  is_current BOOL,
  source_system STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  is_deleted BOOL
);

CREATE OR REPLACE TABLE `{canonical_dataset}.dim_customer` (
  customer_sk INT64,
  customer_id_bk STRING,
  email STRING,
  phone STRING,
  full_name STRING,
  first_name STRING,
  last_name STRING,
  marketing_opt_in BOOL,
  lifetime_value NUMERIC,
  effective_start_at TIMESTAMP,
  effective_end_at TIMESTAMP,
  is_current BOOL,
  source_system STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  is_deleted BOOL
);

CREATE OR REPLACE TABLE `{canonical_dataset}.warehouse` (
  warehouse_sk INT64,
  warehouse_code STRING,
  name STRING,
  address_json STRING,
  timezone STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE OR REPLACE TABLE `{canonical_dataset}.sales_order_header` (
  order_sk INT64,
  order_number STRING,
  customer_sk INT64,
  order_status STRING,
  order_channel STRING,
  order_currency STRING,
  order_datetime TIMESTAMP,
  subtotal_amount NUMERIC,
  discount_amount NUMERIC,
  tax_amount NUMERIC,
  shipping_amount NUMERIC,
  total_amount NUMERIC,
  billing_address_sk INT64,
  shipping_address_sk INT64,
  source_system STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE OR REPLACE TABLE `{canonical_dataset}.sales_order_line` (
  order_line_sk INT64,
  order_sk INT64,
  product_sk INT64,
  line_number INT64,
  quantity_ordered NUMERIC,
  unit_price NUMERIC,
  discount_amount NUMERIC,
  tax_amount NUMERIC,
  total_line_amount NUMERIC,
  fulfillment_status STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE OR REPLACE TABLE `{canonical_dataset}.payment` (
  payment_sk INT64,
  order_sk INT64,
  payment_method STRING,
  provider STRING,
  transaction_id STRING,
  payment_amount NUMERIC,
  captured_at TIMESTAMP,
  status STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE OR REPLACE TABLE `{canonical_dataset}.refund` (
  refund_sk INT64,
  order_sk INT64,
  payment_sk INT64,
  refund_amount NUMERIC,
  refund_reason STRING,
  refunded_at TIMESTAMP,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE OR REPLACE TABLE `{canonical_dataset}.shipment` (
  shipment_sk INT64,
  order_sk INT64,
  warehouse_sk INT64,
  carrier STRING,
  service_level STRING,
  tracking_number STRING,
  shipped_at TIMESTAMP,
  delivered_at TIMESTAMP,
  status STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE OR REPLACE TABLE `{canonical_dataset}.shipment_item` (
  shipment_item_sk INT64,
  shipment_sk INT64,
  order_line_sk INT64,
  product_sk INT64,
  quantity_shipped NUMERIC,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE OR REPLACE TABLE `{canonical_dataset}.inventory_snapshot_daily` (
  snapshot_date DATE,
  product_sk INT64,
  warehouse_sk INT64,
  on_hand_qty NUMERIC,
  allocated_qty NUMERIC,
  available_qty NUMERIC
);
