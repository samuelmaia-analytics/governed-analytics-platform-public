from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from app.components.analytics import (
    cohort_retention,
    filtered_seller_order_count,
    valid_item_grain,
)
from src.semantic_layer import build_cohort_slice, build_seller_slice


@pytest.fixture
def fact():
    return pd.DataFrame(
        {
            "order_id": ["a", "a", "b", "c", "d", "e", "f"],
            "order_item_id": [1, 2, 1, 1, 1, 1, 1],
            "customer_unique_id": ["u", "u", "v", "u", "v", None, "v"],
            "purchase_cohort_month": ["2024-01"] * 7,
            "cohort_order_month_number": [0, 0, 0, 1, 2, 1, 1],
            "order_purchase_timestamp": pd.to_datetime(
                [
                    "2024-01-01",
                    "2024-01-01",
                    "2024-01-31",
                    "2024-02-29",
                    "2024-03-10",
                    "2024-02-12",
                    None,
                ]
            ),
            "total_item_value": [10.10, 20.20, 30.30, 40.40, 50.50, 60.60, 70.70],
            "seller_key": ["s1", "s2", "s1", "s1", "s2", "s3", "s1"],
            "seller_state": ["SP", "SP", "SP", "SP", "SP", "RJ", "SP"],
            "seller_volume_tier": [
                "core",
                "scaled",
                "core",
                "core",
                "scaled",
                "core",
                "core",
            ],
            "seller_avg_delivery_days": [3.0] * 7,
            "seller_delay_rate": [0.0] * 7,
            "review_score_mean": [None] * 7,
            "is_delayed": [False] * 7,
        }
    )


def test_seller_value_and_filtered_distinct_orders_reconcile(fact):
    sellers = build_seller_slice(fact)
    values = dict(zip(sellers["seller_key"], sellers["gross_item_value"], strict=True))
    assert Decimal(str(round(values["s1"], 2))) == Decimal("151.50")
    sp = sellers.loc[sellers["seller_state"].eq("SP")]
    assert int(sp["seller_order_count"].sum()) == 6
    assert filtered_seller_order_count(fact, sp) == 5
    core_sp = sp.loc[sp["seller_volume_tier"].eq("core")]
    assert filtered_seller_order_count(fact, core_sp) == 4
    assert filtered_seller_order_count(fact, sp.iloc[:0]) == 0
    same_seller_order = fact.copy()
    seller_keys = ["seller_key", "seller_state", "seller_volume_tier"]
    same_seller_order.loc[1, seller_keys] = same_seller_order.loc[0, seller_keys]
    row = build_seller_slice(same_seller_order).set_index("seller_key").loc["s1"]
    assert row["gross_item_value"] == pytest.approx(171.70)
    assert row["avg_ticket"] * row["seller_order_count"] == pytest.approx(137.36)
    with pytest.raises(pd.errors.MergeError):
        filtered_seller_order_count(fact, pd.concat([sp, sp]))


def test_cohort_counts_population_ticket_and_incomplete_window(fact):
    cohort = cohort_retention(build_cohort_slice(fact)).set_index(
        "cohort_order_month_number"
    )
    assert cohort.loc[0, "customers"] == 2
    assert cohort.loc[0, "orders"] == 2
    assert cohort.loc[0, "avg_order_ticket"] == pytest.approx(30.30)
    assert cohort.loc[0, "avg_ticket"] == pytest.approx(20.20)
    assert cohort.loc[1, "retention_rate"] == 50
    assert pd.isna(cohort.loc[2, "retention_rate"])


def test_no_leakage_from_duplicate_or_invalid_cohort_keys():
    cells = pd.DataFrame(
        {
            "purchase_cohort_month": [
                "2024-01",
                "2024-01",
                "2024-01",
                "2024-02",
                "2024-03",
                "2024-03",
                "2024-03",
            ],
            "cohort_order_month_number": [0, 0, 1, 0, 0, 1, None],
            "customers": [1, 2, 1, 0, 1, 2, 1],
        }
    )
    retention = cohort_retention(cells)
    assert retention["retention_rate"].dropna().tolist() == [100]
    assert cohort_retention(cells.iloc[:0]).empty


def test_item_grain_rejects_null_or_duplicate_keys(fact):
    assert valid_item_grain(fact)
    assert not valid_item_grain(pd.concat([fact, fact.iloc[:1]]))
    fact.loc[0, "order_id"] = None
    assert not valid_item_grain(fact)
