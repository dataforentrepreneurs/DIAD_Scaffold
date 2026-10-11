{{ config(
    materialized = 'view'
) }}

select
    cast(order_sk as string) as order_id_bk,
    *
from {{ source('ecommerce_raw', 'payment') }}
