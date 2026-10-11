{{ config(
    materialized = 'view'
) }}

with src as (

    select
        uid,
        email,
        phoneNumber   as phone_number_raw,
        displayName   as display_name,
        disabled,
        emailVerified as email_verified,
        createdAt     as created_at_raw,
        lastLoginAt   as last_login_at_raw,
        providerIds   as provider_ids,
        customClaims  as custom_claims,
        _read_ts
    from {{ ref('firebase_auth_users_consolidated') }}

)

select
    uid,
    lower(trim(email)) as email,
    phone_number_raw   as phone_number,
    phone_number_raw   as phone_e164,  -- temporary: treat raw phone as "normalized"
    display_name,
    provider_ids,
    disabled,
    email_verified,

    -- parse Firebase timestamps into proper TIMESTAMPs
    safe.parse_timestamp('%Y-%m-%d %H:%M:%S.%f UTC', created_at_raw)    as created_at,
    safe.parse_timestamp('%Y-%m-%d %H:%M:%S.%f UTC', last_login_at_raw) as last_login_at,

    _read_ts,
    custom_claims
from src
