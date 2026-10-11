{{ config(
    materialized = 'view'
) }}

select *
from {{ ref('firestore_orders_consolidated') }}