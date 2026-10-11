{{ config(
    materialized = 'view'
) }}

select
  -- use the warehouse key as our business key in staging
  cast(customer_sk as string) as customer_id_bk,

  -- if you later want a hashed SK instead of casting, you can use this macro:
  {{ surrogate_key(['cast(customer_sk as string)']) }} as customer_sk,

  lower(trim(email)) as email,
  -- uncomment if you want E.164 normalization later
  {{ e164_phone('phone') }} as phone_e164,

  phone as phone_raw,
  full_name,
  marketing_opt_in
from {{ source('ecommerce_raw', 'dim_customer') }}
