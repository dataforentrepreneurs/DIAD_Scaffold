{{ config(
    materialized = 'table'
) }}

with customers as (

    select
        customer_sk,
        customer_id_bk,
        primary_uid
    from {{ ref('dim_customer') }}

),

identities as (

    select
        identity_sk,
        uid
    from {{ ref('dim_identity_account') }}

)

select
    c.customer_sk,
    c.customer_id_bk,
    i.identity_sk
from customers c
join identities i
    on c.primary_uid = i.uid
where c.primary_uid is not null
