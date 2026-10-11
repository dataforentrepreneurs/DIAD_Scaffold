{{ config(
    materialized = 'table'
) }}

with customers as (

    -- Canonical customers from ingest
    select
        customer_sk,
        customer_id_bk,
        email,
        phone_raw,
        full_name,
        marketing_opt_in
    from {{ ref('stg_dim_customer') }}

),

identities as (

    -- App identities from Firebase auth
    select
        uid,
        email,
        phone_e164,
        created_at,
        last_login_at
    from {{ ref('stg_firebase_auth_users') }}

),

matched as (

    -- Simple email-based match (can extend later to phone, etc.)
    select
        c.customer_sk,
        c.customer_id_bk,
        c.email,
        c.phone_raw,
        c.full_name,
        c.marketing_opt_in,

        i.uid                as primary_uid,
        i.phone_e164         as primary_phone_e164,
        i.created_at         as first_login_at,
        i.last_login_at      as last_login_at
    from customers c
    left join identities i
        on lower(c.email) = lower(i.email)

)

select
    *
from matched
