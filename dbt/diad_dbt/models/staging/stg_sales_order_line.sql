{{ config(
    materialized = 'view'
) }}

select
    cast(order_sk as string) as order_id_bk,
    cast(product_sk as string) as product_id_bk,
    *
from {{ source('ecommerce_raw', 'sales_order_line') }}
