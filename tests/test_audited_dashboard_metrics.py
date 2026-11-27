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


def test_public_seller_delay_uses_only_observable_deliveries(fact):
    fact["order_delivered_customer_date"] = pd.to_datetime(
        ["2024-01-06", None, "2024-01-04", None, None, None, None]
    )
    fact["order_estimated_delivery_date"] = pd.Timestamp("2024-01-05")
    fact["delivery_time_days"] = [5.0, None, 3.0, None, None, None, None]

    sellers = build_seller_slice(fact, observed_delivery_only=True).set_index("seller_key")

    assert sellers.loc["s1", "delay_rate"] == pytest.approx(0.5)
    assert sellers.loc["s1", "avg_delivery_time_days"] == pytest.approx(4.0)
    assert pd.isna(sellers.loc["s2", "delay_rate"])


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


@pytest.mark.parametrize("with_first_purchase", [False, True])
def test_controlled_order_month_normalizes_to_first_purchase(fact, with_first_purchase):
    # Published Python and dbt rows carry the current order month.
    fact["purchase_cohort_month"] = fact["order_purchase_timestamp"].dt.strftime(
        "%Y-%m"
    )
    if with_first_purchase:
        fact["customer_first_purchase_timestamp"] = fact["customer_unique_id"].map(
            {"u": pd.Timestamp("2024-01-01"), "v": pd.Timestamp("2024-01-31")}
        )
    repeated_item = fact.iloc[[3]].assign(order_item_id=2, total_item_value=9.60)
    fact = pd.concat([fact, repeated_item], ignore_index=True)
    # Wrong offset and inconsistent month must never create an extra order.
    invalid = fact.iloc[[3, 3]].assign(
        order_id=["bad-offset", "bad-month"],
        cohort_order_month_number=[2, 1],
        purchase_cohort_month=["2024-02", "2023-12"],
    )
    if with_first_purchase:
        invalid_first = fact.iloc[[3]].assign(
            order_id="bad-first-purchase",
            customer_first_purchase_timestamp="2024-02-01",
        )
        invalid = pd.concat([invalid, invalid_first], ignore_index=True)
    cohort = cohort_retention(
        build_cohort_slice(pd.concat([fact, invalid], ignore_index=True))
    ).set_index("cohort_order_month_number")

    assert cohort["purchase_cohort_month"].unique().tolist() == ["2024-01"]
    assert cohort["customers"].tolist() == [2, 1, 1]
    assert cohort["orders"].tolist() == [2, 1, 1]
    assert cohort["items"].tolist() == [3, 2, 1]
    assert cohort["gross_item_value"].tolist() == pytest.approx([60.60, 50.00, 50.50])
    assert cohort["avg_order_ticket"].tolist() == pytest.approx([30.30, 50.00, 50.50])
    assert cohort.loc[1, "retention_rate"] == 50
    assert pd.isna(cohort.loc[2, "retention_rate"])


def test_cohort_excludes_ambiguous_or_unobservable_acquisition(fact):
    conflicting_m0 = fact.iloc[[3]].assign(
        order_id="ambiguous",
        purchase_cohort_month="2024-02",
        cohort_order_month_number=0,
    )
    cohort = build_cohort_slice(pd.concat([fact, conflicting_m0], ignore_index=True))
    assert cohort["cohort_order_month_number"].tolist() == [0, 2]
    assert cohort["orders"].tolist() == [1, 1]
    assert build_cohort_slice(fact.drop(columns="order_purchase_timestamp")).empty

    false_baseline = fact.copy()
    false_baseline.loc[[0, 1, 3], "cohort_order_month_number"] = [1, 1, 0]
    false_baseline.loc[3, "purchase_cohort_month"] = "2024-02"
    cohort = build_cohort_slice(false_baseline)
    assert cohort["purchase_cohort_month"].tolist() == ["2024-01", "2024-01"]
    assert cohort["cohort_order_month_number"].tolist() == [0, 2]
