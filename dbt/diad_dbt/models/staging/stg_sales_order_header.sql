{{ config(
    materialized = 'view'
) }}

select
    cast(order_sk as string) as order_id_bk,
    cast(customer_sk as string) as customer_id_bk,
    *
from {{ source('ecommerce_raw', 'sales_order_header') }}

