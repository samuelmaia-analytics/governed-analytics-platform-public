"""Generate proposed demo data from formulas only; never read source datasets."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

GENERATOR_VERSION = "gap-synthetic-demo-v2"


def generate(rows: int = 100_001) -> pd.DataFrame:
    if rows < 2:
        raise ValueError("At least two synthetic rows are required.")
    i = np.arange(rows)
    weights = np.arange(1, 102)
    seller_counts = rows * weights // weights.sum()
    seller_counts[: rows - int(seller_counts.sum())] += 1
    seller_numbers = np.repeat(np.arange(101), seller_counts)
    purchased = pd.Timestamp("2019-01-01") + pd.to_timedelta(i // 100, unit="D")
    first_purchase = pd.Timestamp("2019-01-01") + pd.to_timedelta(
        (i % 25001) // 100, unit="D"
    )
    dispatch_days = 1.0 + i % 2
    carrier_days = 2.0 + i % 3
    delivered_days = dispatch_days + carrier_days
    shipped = i % 10 == 0
    delivered = pd.Series(purchased + pd.to_timedelta(delivered_days, unit="D"))
    delivered.loc[shipped] = pd.NaT
    price = (1000 + i % 19000) / 100
    freight = (200 + i % 1800) / 100

    def tokens(prefix: str, values):
        return [
            prefix
            + "_"
            + hashlib.sha256(
                f"{GENERATOR_VERSION}:{prefix}:{int(v)}".encode()
            ).hexdigest()[:16]
            for v in values
        ]

    frame = pd.DataFrame(
        {
            "order_id": tokens("order_id", i),
            "order_item_id": 1 + i % 3,
            "customer_unique_id": tokens("customer_unique_id", i % 25001),
            "order_status": np.where(shipped, "shipped", "delivered"),
            "order_purchase_timestamp": purchased,
            "order_delivered_customer_date": delivered,
            "order_estimated_delivery_date": purchased + pd.to_timedelta(5, unit="D"),
            "order_date": purchased.date,
            "order_year": purchased.year.astype("int64"),
            "order_month": purchased.month.astype("int64"),
            "purchase_cohort_month": first_purchase.strftime("%Y-%m"),
            "cohort_order_month_number": (purchased.year - first_purchase.year) * 12
            + purchased.month
            - first_purchase.month,
            "customer_order_sequence": 1 + i // 25001,
            "is_first_order": i < 25001,
            "seller_key": tokens("seller_id", seller_numbers),
            "delivery_time_days": np.where(shipped, np.nan, delivered_days),
            "seller_dispatch_time_days": dispatch_days,
            "carrier_delivery_time_days": np.where(shipped, np.nan, carrier_days),
            "estimated_delay_days": np.where(shipped, np.nan, delivered_days - 5),
            "is_delayed": ~shipped & (delivered_days > 5),
            "price": price,
            "freight_value": freight,
            "freight_to_price_ratio": freight / price,
            "total_item_value": price + freight,
            "payment_type_mode": np.where(i % 2 == 0, "credit_card", "debit_card"),
            "review_score_mean": np.where(shipped, np.nan, 1.0 + i % 5),
            "product_category_name": [f"synthetic_category_{n}" for n in i % 5],
            "product_category_name_english": [f"synthetic_category_{n}" for n in i % 5],
            "customer_state": np.take(["SP", "RJ", "MG", "PR"], i % 4),
            "seller_state": np.take(["PR", "MG", "RJ", "SP"], seller_numbers % 4),
        }
    )
    by_seller = frame.groupby("seller_key")
    frame["seller_order_count"] = by_seller["order_id"].transform("nunique")
    frame["seller_avg_delivery_days"] = by_seller["delivery_time_days"].transform(
        "mean"
    )
    frame["seller_delay_rate"] = by_seller["is_delayed"].transform("mean")
    frame["seller_volume_tier"] = pd.cut(
        frame["seller_order_count"],
        bins=[-1, 25, 100, 500, float("inf")],
        labels=["long_tail", "scaled", "core", "strategic"],
    ).astype(str)
    # Preserve the contract's column order without reading any source dataset.
    columns = list(frame.columns)
    for name in [
        "seller_volume_tier",
        "seller_order_count",
        "seller_avg_delivery_days",
        "seller_delay_rate",
    ]:
        columns.remove(name)
    offset = columns.index("seller_key") + 1
    columns[offset:offset] = [
        "seller_volume_tier",
        "seller_order_count",
        "seller_avg_delivery_days",
        "seller_delay_rate",
    ]
    return frame[columns]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an existing fixture.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    generate().to_parquet(args.output, index=False)
    print("Synthetic candidate generated; public authorization remains Needs Review.")
