from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from scripts.generate_synthetic_public_demo import generate
from src.data_quality import run_data_quality_checks
from src.publication_gate import evaluate_operational_publication_gate
from src.publish_dashboard import (
    load_domain_policy,
    load_privacy_contract,
    validate_privacy_controls,
)
from src.schema_contract_components.checks import validate_contract

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def synthetic_frame():
    return generate()


def test_formulas_are_deterministic_and_have_no_direct_identifiers():
    first = generate(20)
    pd.testing.assert_frame_equal(first, generate(20))
    assert not {"customer_email", "customer_id", "customer_document", "phone"} & set(
        first
    )
    assert (
        first.loc[first.order_status == "shipped", "order_delivered_customer_date"]
        .isna()
        .all()
    )


def test_seller_grain_cardinality_totals_nulls_and_aggregates(synthetic_frame):
    frame = synthetic_frame
    assert frame["seller_key"].nunique() == 101
    assert not frame.duplicated(["order_id", "order_item_id"]).any()
    assert frame["order_id"].nunique() == len(frame) == 100001
    required = [
        "order_id",
        "order_item_id",
        "customer_unique_id",
        "seller_key",
        "price",
        "freight_value",
        "total_item_value",
    ]
    assert not frame[required].isna().any().any()
    by = frame.groupby("seller_key")
    for column in [
        "seller_order_count",
        "seller_avg_delivery_days",
        "seller_delay_rate",
        "seller_volume_tier",
        "seller_state",
    ]:
        assert (by[column].nunique(dropna=False) == 1).all()
    pd.testing.assert_series_equal(
        frame["seller_order_count"],
        by["order_id"].transform("nunique"),
        check_names=False,
    )
    pd.testing.assert_series_equal(
        frame["seller_avg_delivery_days"],
        by["delivery_time_days"].transform("mean"),
        check_names=False,
    )
    pd.testing.assert_series_equal(
        frame["seller_delay_rate"],
        by["is_delayed"].transform("mean"),
        check_names=False,
    )
    assert int(by["seller_order_count"].first().sum()) == len(frame)
    assert (
        abs(
            frame["total_item_value"].sum()
            - frame["price"].sum()
            - frame["freight_value"].sum()
        )
        < 1e-6
    )
    shipped = frame.order_status == "shipped"
    assert frame.loc[shipped, "delivery_time_days"].isna().all()
    assert not frame.loc[shipped, "is_delayed"].any()
    actual_days = (
        frame.order_delivered_customer_date - frame.order_purchase_timestamp
    ).dt.total_seconds() / 86400
    pd.testing.assert_series_equal(
        frame.delivery_time_days, actual_days, check_names=False
    )
    assert set(frame.seller_volume_tier) == {"long_tail", "scaled", "core", "strategic"}


def test_synthetic_fixture_meets_existing_published_contract(synthetic_frame):
    contract = json.loads(
        (ROOT / "contracts/published/fact_orders_dashboard.contract.json").read_text()
    )
    checks = validate_contract(contract, load_dataset_fn=lambda _: synthetic_frame)
    assert len(checks) == 38
    assert all(check.status == "PASS" for check in checks)
    privacy = load_privacy_contract()
    privacy_checks = validate_privacy_controls(
        synthetic_frame, privacy, load_domain_policy(privacy)
    )
    assert len(privacy_checks) == 16
    assert all(check.status == "PASS" for check in privacy_checks)


def test_demo_does_not_bypass_generic_quality_mismatch(synthetic_frame):
    quality = run_data_quality_checks(synthetic_frame)
    failed = [check for check in quality["checks"] if check["status"] == "FAIL"]
    assert {check["check_name"] for check in failed} == {
        "revenue_accepted_range",
        "revenue_no_negative",
        "customer_email_max_null",
    }
    gate = evaluate_operational_publication_gate(
        total_checks=len(quality["checks"]),
        pass_checks=sum(check["status"] == "PASS" for check in quality["checks"]),
        warn_checks=0,
        fail_checks=len(failed),
        critical_failures=0,
    )
    assert gate.decision == "BLOCKED"


def test_real_app_entrypoint_uses_only_proposed_fixture(tmp_path, synthetic_frame):
    import app.context as context

    fixture = tmp_path / "synthetic.parquet"
    synthetic_frame.to_parquet(fixture, index=False)
    original_read = pd.read_parquet

    def only_synthetic(path, *args, **kwargs):
        assert Path(path).resolve() == fixture.resolve(), (
            "Attempted to read another dataset"
        )
        result = original_read(path, *args, **kwargs)
        result.attrs["quality_dataset"] = "fact_orders_dashboard"
        return result

    def forbidden_csv(*_args, **_kwargs):
        raise AssertionError("Demo attempted to read an unrelated CSV")

    with (
        patch.object(context, "DEFAULT_SAMPLE_DATASET", fixture),
        patch.object(context, "DEFAULT_PUBLISHED_DATASET", tmp_path / "absent.csv"),
        patch.object(
            context,
            "generate_markdown_reports",
            side_effect=AssertionError("Report write"),
            create=True,
        ),
        patch.object(pd, "read_parquet", side_effect=only_synthetic),
        patch.object(pd, "read_csv", side_effect=forbidden_csv),
    ):
        context._build_context_from_dataframe.clear()
        app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=45).run()
        assert not app.exception
        assert any("GOVERNED ANALYTICS PLATFORM" in title.value for title in app.title)
        assert any(
            any(term in str(item.value).lower() for term in ("sample", "amostra"))
            for item in app.warning
        )
