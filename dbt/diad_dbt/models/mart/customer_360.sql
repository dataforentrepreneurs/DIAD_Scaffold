with by_order as (
  select
    cast(h.customer_sk as string) as customer_sk_str,
    count(distinct h.order_sk) as orders_count,
    sum(h.total_amount) as ltv,
    max(h.order_datetime) as last_order_at,
    min(h.order_datetime) as first_order_at
  from {{ ref('sales_order_header') }} h
  group by 1
),
by_login as (
  select
    cast(c.customer_sk as string) as customer_sk_str,
    c.last_login_at as last_login_at,
    c.first_login_at as first_seen_auth
  from {{ ref('dim_customer') }} c
)
select
  c.customer_sk, c.customer_id_bk, c.primary_uid, c.email, c.primary_phone_e164, c.full_name, c.marketing_opt_in,
  ifnull(o.orders_count, 0) as orders_count, ifnull(o.ltv, 0) as ltv, o.first_order_at, o.last_order_at,
  l.first_seen_auth, l.last_login_at
from {{ ref('dim_customer') }} c
left join by_order o on cast(c.customer_sk as string) = o.customer_sk_str
left join by_login l on cast(c.customer_sk as string) = l.customer_sk_str
