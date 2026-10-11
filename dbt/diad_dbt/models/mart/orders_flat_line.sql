select
  h.order_sk, cast(h.order_sk as string) as order_id_bk, h.order_datetime, h.order_status, h.order_channel, h.order_currency,
  h.subtotal_amount, h.discount_amount, h.tax_amount, h.shipping_amount, h.total_amount,
  c.customer_sk, c.customer_id_bk, c.email, c.primary_phone_e164, c.primary_uid,
  l.order_line_sk, l.line_number, l.quantity_ordered, l.unit_price,
  l.discount_amount as line_discount_amount, l.tax_amount as line_tax_amount, l.total_line_amount,
  p.product_id_bk, p.sku, p.product_name, p.brand, p.category_path
from {{ ref('sales_order_line') }} l
join {{ ref('sales_order_header') }} h on cast(h.order_sk as string) = cast(l.order_sk as string)
left join {{ ref('dim_customer') }} c on cast(c.customer_sk as string) = cast(h.customer_sk as string)
left join {{ ref('stg_dim_product') }} p on cast(p.product_sk as string) = cast(l.product_sk as string)
