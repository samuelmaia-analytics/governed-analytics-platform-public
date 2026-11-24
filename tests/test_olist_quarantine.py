from __future__ import annotations

import json
from functools import partial

import pandas as pd
import pytest

import src.build_analytics as build
from src.analytics.olist import quarantine
from src.analytics.olist.cleaning import clean_order_items
from src.analytics.olist.transformations import remove_obvious_inconsistencies
from src.public_content import read_public_content


def test_rejects_only_filtered_rows_and_keeps_source(tmp_path):
    source = pd.DataFrame(
        {
            "order_id": ["good", "good", "bad", "missing"],
            "order_item_id": [1, 1, 2, 3],
            "product_id": ["p", "p", "p", None],
            "seller_id": ["s"] * 4,
            "price": [10, 10, -2, 5],
            "freight_value": [1] * 4,
        }
    )
    directory = tmp_path / "data/quarantine"
    journal = quarantine.RejectionJournal(directory, "run-1")
    original = source.copy(deep=True)
    accepted = clean_order_items(source, reject=partial(journal.capture, "olist_items"))
    journal.persist()

    pd.testing.assert_frame_equal(source, original)
    assert accepted["order_id"].tolist() == ["good"]
    evidence = json.loads(journal.path.read_bytes())
    assert evidence["stage"] == "build" and evidence["run_id"] == "run-1"
    assert evidence["publication_authorized"] is False
    assert {entry["dataset"] for entry in evidence["rejections"]} == {"olist_items"}
    assert [
        (entry["rule"], entry["input_index"]) for entry in evidence["rejections"]
    ] == [("duplicate", [1]), ("missing_required_key", [3]), ("negative_price", [2])]
    assert evidence["rejections"][-1]["records"][0]["price"] == -2
    assert read_public_content(journal.path) is None

    previous = journal.path.read_bytes()
    journal.persist()
    assert journal.path.read_bytes() == previous
    corrected = source.iloc[[0, 2]].copy()
    corrected.loc[2, "price"] = 2
    retry = quarantine.RejectionJournal(directory, "run-2")
    accepted = clean_order_items(
        corrected, reject=partial(retry.capture, "olist_items")
    )
    retry.persist()
    assert accepted["order_id"].tolist() == ["good", "bad"]
    assert list(directory.iterdir()) == [journal.path]
    with pytest.raises(ValueError, match="different evidence"):
        quarantine.RejectionJournal(directory, "run-1").persist()
    assert journal.path.read_bytes() == previous


def test_temporal_warning_is_preserved_but_rejected_duration_is_routed(tmp_path):
    frame = pd.DataFrame(
        {
            "order_id": ["warn", "reject"],
            "order_item_id": [1, 1],
            "product_id": ["p"] * 2,
            "seller_id": ["s"] * 2,
            "price": [10] * 2,
            "freight_value": [1] * 2,
            "order_purchase_timestamp": pd.to_datetime(["2020-01-01"] * 2),
            "order_approved_at": pd.to_datetime(["2020-01-05"] * 2),
            "order_delivered_customer_date": pd.to_datetime(
                ["2020-01-03", "2019-12-31"]
            ),
            "delivery_time_days": [2, -1],
        }
    )
    journal = quarantine.RejectionJournal(tmp_path, "run-3")
    accepted = remove_obvious_inconsistencies(
        frame, reject=partial(journal.capture, "fact_orders_enriched")
    )
    assert accepted["order_id"].tolist() == ["warn"]
    assert [entry["rule"] for entry in journal.rejections] == [
        "negative_delivery_duration"
    ]


def test_failed_atomic_write_prevents_gold_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT_DIR", tmp_path)

    def classify(*, quarantine):
        quarantine.capture("orders", "duplicate", pd.DataFrame({"id": ["synthetic"]}))
        quarantine.persist()
        return pd.DataFrame({"id": ["good"]})

    def fail(*args):
        raise OSError("storage error")

    monkeypatch.setattr(build, "build_fact_orders_enriched", classify)
    monkeypatch.setattr(
        build, "save_outputs", lambda _: pytest.fail("Gold must not be written")
    )
    monkeypatch.setattr(quarantine.os, "link", fail)
    with pytest.raises(OSError, match="storage error"):
        build.run_build(run_id="run-4")
    assert list((tmp_path / "data/quarantine").iterdir()) == []
