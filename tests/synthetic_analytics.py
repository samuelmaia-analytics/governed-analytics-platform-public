"""Contract-based analytical sources, generated without historical records."""

import numpy as np
import pandas as pd

ROWS = 112_650
ORDERS = 1_000


def analytical_sources():
    ids = [f"scenario-order-{i:04d}" for i in range(ORDERS)]
    customers = [f"scenario-customer-{i:04d}" for i in range(ORDERS)]
    purchase = pd.Timestamp("2001-01-01") + pd.to_timedelta(
        np.arange(ORDERS) % 60, unit="D"
    )
    delivered = purchase + pd.to_timedelta(
        np.where(np.arange(ORDERS) % 10 == 0, 12, 8), unit="D"
    )
    orders = pd.DataFrame(
        {
            "order_id": ids,
            "customer_id": customers,
            "order_status": "delivered",
            "order_purchase_timestamp": purchase,
            "order_approved_at": purchase + pd.Timedelta(days=1),
            "order_delivered_carrier_date": purchase + pd.Timedelta(days=3),
            "order_delivered_customer_date": delivered,
            "order_estimated_delivery_date": purchase + pd.Timedelta(days=10),
        }
    )
    order_index = np.arange(ROWS) % ORDERS
    seller_index = np.select(
        [order_index < 10, order_index < 60, order_index < 260], [0, 1, 2], default=3
    )
    items = pd.DataFrame(
        {
            "order_id": np.array(ids)[order_index],
            "order_item_id": np.arange(ROWS) // ORDERS + 1,
            "product_id": "scenario-product",
            "seller_id": [f"scenario-seller-{i}" for i in seller_index],
            "shipping_limit_date": purchase.take(order_index) + pd.Timedelta(days=4),
            "price": 100.0,
            "freight_value": 10.0,
        }
    )
    customer_table = pd.DataFrame(
        {
            "customer_id": customers,
            "customer_unique_id": [
                f"scenario-buyer-{i // 2:04d}" for i in range(ORDERS)
            ],
            "customer_zip_code_prefix": 0,
            "customer_city": "synthetic-locality",
            "customer_state": "XX",
        }
    )
    products = pd.DataFrame(
        {
            "product_id": ["scenario-product"],
            "product_category_name": ["synthetic-category"],
            **{
                c: [1.0]
                for c in [
                    "product_name_lenght",
                    "product_description_lenght",
                    "product_photos_qty",
                    "product_weight_g",
                    "product_length_cm",
                    "product_height_cm",
                    "product_width_cm",
                ]
            },
        }
    )
    sellers = pd.DataFrame(
        {
            "seller_id": [f"scenario-seller-{i}" for i in range(4)],
            "seller_zip_code_prefix": 0,
            "seller_city": "synthetic-locality",
            "seller_state": "XX",
        }
    )
    payments = pd.DataFrame(
        {
            "order_id": ids[:-1],
            "payment_sequential": 1,
            "payment_value": 110.0,
            "payment_installments": 1,
            "payment_type": "synthetic-payment",
        }
    )
    reviews = pd.DataFrame(
        {
            "order_id": ids[:-1],
            "review_id": [f"scenario-review-{i}" for i in range(ORDERS - 1)],
            "review_score": 4,
            "review_comment_message": "",
            "review_creation_date": purchase[:-1] + pd.Timedelta(days=13),
            "review_answer_timestamp": purchase[:-1] + pd.Timedelta(days=14),
        }
    )
    translation = pd.DataFrame(
        {
            "product_category_name": ["synthetic-category"],
            "product_category_name_english": ["synthetic-category"],
        }
    )
    return dict(
        zip(
            [
                "olist_orders_dataset.csv",
                "olist_order_items_dataset.csv",
                "olist_customers_dataset.csv",
                "olist_products_dataset.csv",
                "olist_sellers_dataset.csv",
                "olist_order_payments_dataset.csv",
                "olist_order_reviews_dataset.csv",
                "product_category_name_translation.csv",
            ],
            [
                orders,
                items,
                customer_table,
                products,
                sellers,
                payments,
                reviews,
                translation,
            ],
            strict=True,
        )
    )
