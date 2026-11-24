from __future__ import annotations

import pandas as pd
import pytest
from synthetic_fixtures import (
    expected_privacy_failures,
    orders_missing_customer_id,
    orders_missing_order_column,
    orders_with_high_privacy_risk,
    unprotected_published_frame,
    valid_orders,
)


@pytest.mark.parametrize(
    "factory",
    [
        valid_orders,
        orders_missing_customer_id,
        orders_missing_order_column,
        orders_with_high_privacy_risk,
    ],
)
def test_synthetic_scenarios_are_deterministic_and_independent(factory):
    first = factory()
    pd.testing.assert_frame_equal(first, factory())
    first.loc[0, "revenue"] = -1000
    assert factory().loc[0, "revenue"] > 0


def test_generators_do_not_load_dataset_files(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Synthetic generators must not load dataset files.")

    monkeypatch.setattr(pd, "read_csv", forbidden)
    monkeypatch.setattr(pd, "read_parquet", forbidden)
    assert len(valid_orders()) == 3
    assert orders_missing_customer_id()["customer_id"].isna().sum() == 1
    assert set(valid_orders()) - set(orders_missing_order_column()) == {"order_id"}
    assert "health_status" in orders_with_high_privacy_risk()
    frame = unprotected_published_frame(
        ["order_id", "customer_unique_id", "seller_key", "customer_state"]
    )
    assert "seller_key" not in frame
    assert frame["customer_state"].isna().all()
    records = expected_privacy_failures()
    assert len(records) == 16
    assert sum(record["status"] == "PASS" for record in records) == 4
    assert sum(record["status"] == "FAIL" for record in records) == 12


def test_valid_scenario_uses_reserved_contact_domain_and_unique_synthetic_keys():
    frame = valid_orders()
    assert frame["customer_email"].str.endswith("@example.invalid").all()
    assert frame["order_id"].str.startswith("scenario-order-").all()
    assert frame["customer_id"].str.startswith("scenario-customer-").all()
    assert not frame["order_id"].duplicated().any()
