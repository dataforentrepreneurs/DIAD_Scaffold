{{ config(
    materialized = 'view'
) }}

select
    *
from {{ source('ecommerce_raw', 'dim_product') }}