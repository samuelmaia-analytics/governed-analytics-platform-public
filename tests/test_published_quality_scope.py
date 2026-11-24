from __future__ import annotations

import hashlib
import json

import pytest

from scripts.generate_synthetic_public_demo import generate
from src.data_quality import run_data_quality_checks
from src.public_distribution_authorization import (
    REQUIRED_ARTIFACTS,
    public_demo_authorization_complete,
)
from src.publication_gate import evaluate_operational_publication_gate


@pytest.fixture(scope="module")
def published():
    return generate()


def test_published_scope_passes_without_inventing_generic_fields(published):
    quality = run_data_quality_checks(published, dataset_name="fact_orders_dashboard")
    assert quality["failed_checks_count"] == 0
    assert quality["quality_failed_checks_count"] == 0
    assert quality["contract_failed_checks_count"] == 0
    assert quality["schema_contract_status"] == "passed"
    assert not {"customer_email", "revenue"} & set(published)
    assert (
        sum(c["rule_source"] == "published_schema_contract" for c in quality["checks"])
        == 38
    )


def test_generic_rules_remain_strict_for_their_original_scope(published):
    quality = run_data_quality_checks(published)
    assert {c["check_name"] for c in quality["checks"] if c["status"] == "FAIL"} == {
        "revenue_accepted_range",
        "revenue_no_negative",
        "customer_email_max_null",
    }


def test_missing_published_column_is_a_contract_failure(published):
    broken = published.drop(columns="customer_unique_id")
    quality = run_data_quality_checks(broken, dataset_name="fact_orders_dashboard")
    assert quality["schema_contract_status"] == "failed"
    assert quality["contract_failed_checks_count"] > 0


def test_legitimate_negative_value_remains_a_quality_failure(published):
    broken = published.copy()
    broken.loc[0, "total_item_value"] = -1
    quality = run_data_quality_checks(broken, dataset_name="fact_orders_dashboard")
    assert quality["schema_contract_status"] == "passed"
    assert quality["quality_failed_checks_count"] > 0
    assert any(
        c["check_name"] == "published_total_item_value_non_negative"
        and c["status"] == "FAIL"
        for c in quality["checks"]
    )


def test_missing_key_cannot_crash_or_evade_contract_gate(published):
    quality = run_data_quality_checks(
        published.drop(columns="order_id"), dataset_name="fact_orders_dashboard"
    )
    assert quality["schema_contract_status"] == "failed"
    assert quality["failed_checks_count"] > 0


def test_unknown_quality_scope_fails_closed(published):
    with pytest.raises(ValueError):
        run_data_quality_checks(published, dataset_name="unknown")


def test_published_grain_uses_composite_key_and_still_rejects_duplicates(published):
    multiple_items = published.copy()
    multiple_items.loc[1, "order_id"] = multiple_items.loc[0, "order_id"]
    assert (
        run_data_quality_checks(multiple_items, dataset_name="fact_orders_dashboard")[
            "failed_checks_count"
        ]
        == 0
    )
    multiple_items.loc[1, "order_item_id"] = multiple_items.loc[0, "order_item_id"]
    result = run_data_quality_checks(
        multiple_items, dataset_name="fact_orders_dashboard"
    )
    assert any(
        c["check_name"] == "published_primary_key_unique" and c["status"] == "FAIL"
        for c in result["checks"]
    )


def test_authorization_is_rechecked_after_cached_quality(monkeypatch, published):
    import app.context as context

    frame = published.copy()
    frame.attrs["quality_dataset"] = "fact_orders_dashboard"
    monkeypatch.setattr(context, "load_input_dataframe", lambda _: frame)
    grants = iter([True, False])
    monkeypatch.setattr(
        context, "public_demo_authorization_complete", lambda _: next(grants)
    )
    context._build_context_from_dataframe.clear()
    first = context.build_context("en-US")
    second = context.build_context("en-US")
    assert first.public_distribution_gate.decision == "APPROVED"
    assert second.public_distribution_gate.decision == "BLOCKED"
    assert second.quality_results["failed_checks_count"] == 0


def test_public_gate_requires_all_exact_grants_even_when_quality_passes(
    tmp_path, published
):
    quality = run_data_quality_checks(published, dataset_name="fact_orders_dashboard")
    registry = tmp_path / "config/public_distribution_authorizations.json"
    registry.parent.mkdir()
    (registry.parent / "public_revocations.json").write_text(
        json.dumps(
            {
                "version": 1,
                "revoked_sha256": [],
                "revoked_artifacts": [],
            }
        )
    )
    registry.write_text(json.dumps({"version": 1, "authorizations": []}))

    def gate():
        return evaluate_operational_publication_gate(
            total_checks=len(quality["checks"]),
            pass_checks=len(quality["checks"]),
            warn_checks=0,
            fail_checks=0,
            critical_failures=0,
            public_authorization_complete=public_demo_authorization_complete(tmp_path),
        )

    assert gate().decision == "BLOCKED"
    assert gate().quality_score == 100
    grants = []
    for name, purpose in REQUIRED_ARTIFACTS.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic authorization-test bytes")
        grants.append(
            {
                "file": name,
                "purpose": purpose,
                "audience": "public",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "status": "Needs Review",
                "publication_authorized": False,
            }
        )
    registry.write_text(json.dumps({"version": 1, "authorizations": grants}))
    assert gate().decision == "BLOCKED"
    # Positive controls are test-only, never applied to repository manifests.
    for grant in grants:
        grant.update(status="Approved", publication_authorized=True)
    registry.write_text(json.dumps({"version": 1, "authorizations": grants}))
    assert gate().decision == "APPROVED"
    grants[-1]["publication_authorized"] = False
    registry.write_text(json.dumps({"version": 1, "authorizations": grants}))
    assert gate().decision == "BLOCKED"
    grants[-1]["publication_authorized"] = True
    registry.write_text(json.dumps({"version": 1, "authorizations": grants}))
    (tmp_path / next(iter(REQUIRED_ARTIFACTS))).write_bytes(b"changed")
    assert gate().decision == "BLOCKED"
