with lines as (
  select
    order_sk,
    array_agg(struct(order_line_sk, line_number, quantity_ordered, unit_price,
                     discount_amount as line_discount_amount,
                     tax_amount as line_tax_amount,
                     total_line_amount,
                     cast(product_sk as string) as product_id_bk) order by line_number) as items
  from {{ ref('sales_order_line') }}
  group by order_sk
),
ship as (
  select
    order_sk,
    array_agg(struct(cast(shipment_sk as string) as shipment_sk, carrier, tracking_number,
                     shipped_at, delivered_at, status, warehouse_sk)) as shipments
  from {{ ref('shipment') }}
  group by order_sk
),
pay as (
  select
    order_sk,
    array_agg(struct(payment_sk, payment_method, provider, transaction_id,
                     payment_amount, status, captured_at)) as payments
  from {{ ref('payment') }}
  group by order_sk
),
rf as (
  select
    order_sk,
    array_agg(struct(refund_sk, payment_sk, refund_amount, refund_reason, created_at as refunded_at)) as refunds
  from {{ ref('refund') }}
  group by order_sk
)

select
  h.* except(customer_sk),
  c.customer_sk,
  c.primary_uid,
  c.email,
  c.primary_phone_e164,
  ifnull(ship.shipments, []) as shipments,
  ifnull(pay.payments, [])   as payments,
  ifnull(rf.refunds, [])     as refunds,
  lines.items
from {{ ref('sales_order_header') }} h
left join {{ ref('dim_customer') }} c on cast(c.customer_sk as string) = cast(h.customer_sk as string)
left join lines on lines.order_sk = h.order_sk
left join ship  on ship.order_sk = h.order_sk
left join pay   on pay.order_sk = h.order_sk
left join rf    on rf.order_sk = h.order_sk

