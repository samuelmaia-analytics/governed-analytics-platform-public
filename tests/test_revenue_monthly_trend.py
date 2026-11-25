from decimal import Decimal

import duckdb
import pandas as pd
import pytest

from app.components.analytics import valid_item_grain
from app.pages.revenue_analytics import _build_monthly_revenue
from src.data_loader import DEFAULT_PUBLIC_DEMO_DATASET, load_dataset


def test_mom_and_moving_average_require_complete_consecutive_months():
    frame = pd.DataFrame(
        {
            "order_purchase_timestamp": [
                "2024-09-15",
                "2024-01-15",
                "2024-02-12",
                "2024-03-12",
                "2024-04-12",
                "2024-06-12",
                "2024-07-12",
                "2024-08-12",
            ],
            "total_item_value": [50, 20, 100, 0, 200, 300, 600, 900],
        }
    )
    monthly = _build_monthly_revenue(frame).data
    assert monthly.index.astype(str).tolist() == [f"2024-{m:02}" for m in range(1, 10)]
    assert monthly.index[monthly["partial"]].astype(str).tolist() == [
        "2024-01",
        "2024-09",
    ]
    assert monthly.loc["2024-09", "revenue"] == 50
    assert pd.isna(monthly.loc["2024-05", "revenue"])
    assert monthly["mom"].dropna().tolist() == pytest.approx([-100, 100, 50])
    assert monthly["mom"].dropna().index.astype(str).tolist() == [
        "2024-03",
        "2024-07",
        "2024-08",
    ]
    assert monthly["moving_average"].dropna().to_dict() == {
        pd.Period("2024-04", "M"): 100,
        pd.Period("2024-08", "M"): 600,
    }


def test_purchase_timestamps_take_precedence_and_invalid_dates_reconcile():
    frame = pd.DataFrame(
        {
            "order_purchase_timestamp": ["2024-02-01", "2024-02-12", "invalid"],
            "order_year_month": ["2023-01", "2023-01", "2023-01"],
            "total_item_value": [5, 10, 20],
        }
    )
    result = _build_monthly_revenue(frame)
    assert result.undated_items == 1
    assert result.undated_revenue == 20
    assert result.data.index.astype(str).tolist() == ["2024-02"]
    assert result.data.loc["2024-02", "partial"]
    assert result.data["revenue"].sum() + result.undated_revenue == 35


@pytest.mark.parametrize(
    "date_columns",
    [
        {"order_year_month": ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05"]},
        {"order_year": [2024] * 5, "order_month": [1, 2, 3, 4, 5]},
    ],
)
def test_month_only_fallback_excludes_unverified_boundaries(date_columns):
    result = _build_monthly_revenue(
        pd.DataFrame({**date_columns, "total_item_value": [50, 100, 200, 300, 400]})
    )
    monthly = result.data
    assert result.first_purchase is None and result.last_purchase is None
    assert monthly["revenue"].sum() == 1050
    assert monthly["unverified_boundary"].tolist() == [True, False, False, False, True]
    assert monthly["mom"].dropna().tolist() == [100, 50]
    assert monthly["moving_average"].dropna().to_dict() == {
        pd.Period("2024-04", "M"): 200
    }


def test_public_monthly_bars_match_independent_duckdb_totals(monkeypatch):
    monkeypatch.setenv("GAP_PUBLIC_VISITOR_MODE", "true")
    frame = load_dataset(DEFAULT_PUBLIC_DEMO_DATASET)
    assert valid_item_grain(frame)
    assert frame["order_id"].nunique() == 100_001
    with duckdb.connect() as database:
        database.register("fact", frame)
        expected = dict(
            database.sql("""
            select strftime(order_purchase_timestamp, '%Y-%m'),
                   sum(cast(total_item_value as decimal(18,2)))
            from fact
            group by 1
        """).fetchall()
        )

    result = _build_monthly_revenue(frame)
    observed = {
        str(month): Decimal(f"{amount:.2f}")
        for month, amount in result.data["revenue"].items()
    }
    assert result.undated_items == 0
    assert observed == expected
    assert len(observed) == 33
    assert sum(observed.values()) == Decimal("11245072.00")
    assert result.data.index[result.data["partial"]].astype(str).tolist() == ["2021-09"]
    assert result.data["mom"].notna().sum() == 31
    assert result.data["moving_average"].notna().sum() == 30
