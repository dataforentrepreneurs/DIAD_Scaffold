
"""
Generate synthetic CSV seed data for Phase 3.
Outputs: ./seed/*.csv
Row counts controlled by config/client_ingest.json -> ingest.seed_record_counts
"""
from datetime import datetime, timedelta, time
import random, csv, json, os, pathlib,sys
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from gcp_utils import get_run_date

BASE = pathlib.Path(__file__).parent
CFG = json.load(open(BASE.parent.parent / "config" / "client_rawdata.json", "r", encoding="utf-8"))
OUT = BASE / "seed"
OUT.mkdir(exist_ok=True, parents=True)

N_CUSTOMERS = int(CFG["ingest"]["seed_record_counts"]["customers"])
N_PRODUCTS  = int(CFG["ingest"]["seed_record_counts"]["products"])
N_ORDERS    = int(CFG["ingest"]["seed_record_counts"]["orders"])

random.seed(42)

run_date = get_run_date(CFG)

# anchor at local noon to make offsets readable; adjust if you prefer midnight
now = datetime.combine(run_date, time(12, 0, 0))

def ts(offset_days=0):
    return (now + timedelta(days=offset_days)).strftime("%Y-%m-%d %H:%M:%S")

def write_csv(path, rows):
    if not rows: return
    keys = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)

domains = ["example.com","shopmail.com","retailio.io"]
first_names = ["Aarav","Vivaan","Aditya","Vihaan","Ayaan","Ishaan","Kabir","Arjun","Reyansh","Atharv","Ananya","Diya","Ira","Myra","Sara","Aadhya","Anika","Navya","Saanvi","Zara"]
last_names = ["Sharma","Patel","Mehta","Gupta","Singh","Iyer","Das","Nair","Khan","Ghosh"]
brands = ["Aurora","Nimbus","Solace","Vertex","Marina"]
categories = ["Men > Tees > Crew","Men > Shoes > Sneakers","Women > Dresses > Casual","Women > Shoes > Flats","Accessories > Bags > Backpacks"]
colors = ["Red","Blue","Black","White","Green"]
sizes = ["S","M","L","XL"]

# Customers
customers = []
for sk in range(1, N_CUSTOMERS+1):
    fn = random.choice(first_names); ln = random.choice(last_names)
    customers.append({
        "customer_sk": sk, "customer_id_bk": f"CUST-{1000+sk}", "email": f"{fn.lower()}.{ln.lower()}@{random.choice(domains)}",
        "phone": f"+65 8{random.randint(1000000,9999999)}", "full_name": f"{fn} {ln}",
        "first_name": fn, "last_name": ln, "marketing_opt_in": random.choice([True,False]),
        "lifetime_value": round(random.uniform(100,2000),2),
        "effective_start_at": ts(-365), "effective_end_at": "", "is_current": True,
        "source_system": "SEED", "created_at": ts(-30), "updated_at": ts(-1), "is_deleted": False
    })
write_csv(OUT/"dim_customer.csv", customers)

# Products
products = []
for sk in range(1, N_PRODUCTS+1):
    brand = random.choice(brands); cat = random.choice(categories)
    color = random.choice(colors); size = random.choice(sizes)
    parent = f"PSKU-{(sk//3)}" if (sk % 3 == 0 and sk > 3) else ""
    products.append({
        "product_sk": sk, "product_id_bk": f"PROD-{5000+sk}", "sku": f"SKU-{10000+sk}", "parent_sku": parent,
        "product_name": f"{brand} {color} {size}", "brand": brand, "category_path": cat,
        "attributes_json": '{"color":"%s","size":"%s"}' % (color,size),
        "uom": "EA", "status": "ACTIVE", "effective_start_at": ts(-180), "effective_end_at": "",
        "is_current": True, "source_system": "SEED", "created_at": ts(-30), "updated_at": ts(-1), "is_deleted": False
    })
write_csv(OUT/"dim_product.csv", products)

# Warehouses
warehouses = [
    {"warehouse_sk":1,"warehouse_code":"SG-01","name":"Singapore Main","address_json":'{"city":"Singapore","country":"SG","line1":"1 HarbourFront"}',"timezone":"Asia/Singapore","created_at":ts(-60),"updated_at":ts(-1)},
    {"warehouse_sk":2,"warehouse_code":"MY-01","name":"Johor Hub","address_json":'{"city":"Johor Bahru","country":"MY","line1":"1 Nusajaya"}',"timezone":"Asia/Kuala_Lumpur","created_at":ts(-60),"updated_at":ts(-1)}
]
write_csv(OUT/"warehouse.csv", warehouses)

# Orders + lines + payments + refunds + shipments + shipment_items + daily snapshots
order_headers, order_lines, payments, refunds, shipments, shipment_items, snapshots = [],[],[],[],[],[],[]
ol_sk = 1; pay_sk = 1; ref_sk = 1; ship_sk = 1; ship_item_sk = 1

for order_sk in range(1, N_ORDERS+1):
    cust = random.choice(customers)
    day = -random.randint(1,30)
    currency = random.choice(["SGD","USD"])
    channel = random.choice(["WEB","APP","MARKETPLACE"])
    status = random.choice(["NEW","CONFIRMED","CANCELLED","CLOSED"])
    n_lines = random.randint(1,4)

    subs=[]; current=[]
    for ln in range(1,n_lines+1):
        p = random.choice(products); qty = random.randint(1,3); price = round(random.uniform(10,200),2)
        line_total = round(qty*price,2); disc = round(line_total*random.choice([0,0.05,0.10]),2)
        tax = round((line_total - disc)*0.08,2) if currency=="SGD" else 0.0
        total_line_amount = round(line_total - disc + tax,2)
        subs.append((line_total,disc,tax,total_line_amount))
        current.append({
            "order_line_sk": ol_sk, "order_sk": order_sk, "product_sk": p["product_sk"], "line_number": ln,
            "quantity_ordered": qty, "unit_price": price, "discount_amount": disc, "tax_amount": tax,
            "total_line_amount": total_line_amount, "fulfillment_status": random.choice(["UNFULFILLED","PARTIAL","FULFILLED"]),
            "created_at": ts(day), "updated_at": ts(day+1)
        })
        ol_sk += 1
    order_lines.extend(current)

    subtotal = round(sum(x[0] for x in subs),2); discount = round(sum(x[1] for x in subs),2)
    tax = round(sum(x[2] for x in subs),2); shipping = random.choice([0,2.99,4.99,9.99])
    total = round(sum(x[3] for x in subs)+shipping,2)

    order_headers.append({
        "order_sk": order_sk, "order_number": f"ORD-{100000+order_sk}", "customer_sk": cust["customer_sk"],
        "order_status": status, "order_channel": channel, "order_currency": currency, "order_datetime": ts(day),
        "subtotal_amount": subtotal, "discount_amount": discount, "tax_amount": tax,
        "shipping_amount": shipping, "total_amount": total, "billing_address_sk": "", "shipping_address_sk": "",
        "source_system": "SEED", "created_at": ts(day), "updated_at": ts(day+1)
    })

    pay_status = random.choice(["CAPTURED","AUTHORIZED","FAILED","REFUNDED"])
    payments.append({
        "payment_sk": pay_sk, "order_sk": order_sk, "payment_method": random.choice(["CARD","WALLET","PAYNOW","COD"]),
        "provider": random.choice(["Stripe","Adyen","PayPal","GrabPay"]), "transaction_id": f"TXN-{700000+pay_sk}",
        "payment_amount": total if pay_status in ["CAPTURED","REFUNDED"] else round(total*random.uniform(0.2,0.8),2),
        "captured_at": ts(day), "status": pay_status, "created_at": ts(day), "updated_at": ts(day+1)
    })
    if pay_status=="REFUNDED":
        refunds.append({
            "refund_sk": ref_sk, "order_sk": order_sk, "payment_sk": pay_sk,
            "refund_amount": round(total*random.choice([0.2,0.5,1.0]),2),
            "refund_reason": random.choice(["DAMAGED","CUSTOMER_REMORSE","LATE_DELIVERY"]),
            "refunded_at": ts(day+1), "created_at": ts(day+1), "updated_at": ts(day+2)
        })
        ref_sk += 1
    pay_sk += 1

    if status in ["CONFIRMED","CLOSED"] and pay_status in ["CAPTURED","REFUNDED"]:
        shipped = ts(day+1); delivered = ts(day+3)
        shipments.append({
            "shipment_sk": ship_sk, "order_sk": order_sk, "warehouse_sk": random.choice([1,2]),
            "carrier": random.choice(["DHL","NinjaVan","J&T","Qxpress"]), "service_level": random.choice(["STANDARD","EXPRESS"]),
            "tracking_number": f"TRK-{900000+ship_sk}", "shipped_at": shipped, "delivered_at": delivered,
            "status":"DELIVERED","created_at": shipped,"updated_at": delivered
        })
        for l in current:
            shipment_items.append({
                "shipment_item_sk": ship_item_sk, "shipment_sk": ship_sk, "order_line_sk": l["order_line_sk"],
                "product_sk": l["product_sk"], "quantity_shipped": l["quantity_ordered"],
                "created_at": shipped, "updated_at": delivered
            })
            ship_item_sk += 1
        ship_sk += 1

# Daily snapshot
yesterday = (now - timedelta(days=1)).date().isoformat()
for p in products[:50]:
    on = random.randint(5,200); al = random.randint(0,max(0,on-1)); av = on - al
    snapshots.append({"snapshot_date": yesterday, "product_sk": p["product_sk"], "warehouse_sk": 1, "on_hand_qty": on, "allocated_qty": al, "available_qty": av})

# Write all
write_csv(OUT/"dim_customer.csv", customers)
write_csv(OUT/"dim_product.csv", products)
write_csv(OUT/"warehouse.csv", warehouses)
write_csv(OUT/"sales_order_header.csv", order_headers)
write_csv(OUT/"sales_order_line.csv", order_lines)
write_csv(OUT/"payment.csv", payments)
write_csv(OUT/"refund.csv", refunds)
write_csv(OUT/"shipment.csv", shipments)
write_csv(OUT/"shipment_item.csv", shipment_items)
write_csv(OUT/"inventory_snapshot_daily.csv", snapshots)

print("Seed generated at:", OUT)
