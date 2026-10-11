{{ config(
    materialized = 'table'
) }}

with src as (

    select
        uid,
        email,
        phone_number,
        phone_e164,
        display_name,
        provider_ids,
        disabled,
        email_verified,
        created_at,
        last_login_at,
        _read_ts,
        custom_claims
    from {{ ref('stg_firebase_auth_users') }}

)

select
    uid                                   as identity_id_bk,
    {{ surrogate_key(['uid']) }}          as identity_sk,
    uid,                                  -- keep raw uid for joins
    email,
    phone_e164,
    display_name,
    provider_ids,
    disabled,
    email_verified,
    created_at,
    last_login_at,
    _read_ts,
    custom_claims
from src
