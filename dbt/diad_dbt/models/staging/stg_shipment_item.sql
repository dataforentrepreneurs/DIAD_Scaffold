{{ config(
    materialized = 'view'
) }}

select
    cast(product_sk as string) as product_id_bk,
    *
from {{ source('ecommerce_raw', 'shipment_item') }}
