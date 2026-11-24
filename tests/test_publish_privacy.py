from __future__ import annotations

from dataclasses import asdict

import pandas as pd
from synthetic_fixtures import expected_privacy_failures, unprotected_published_frame

from src.data_classification import CLASSIFICATION_ROWS
from src.publish_components.privacy import validate_privacy_controls
from src.publish_dashboard import (
    PUBLISHED_COLUMNS,
    build_published_dashboard_table,
    load_domain_policy,
    load_privacy_contract,
)

EXPECTED_CHECKS = [
    "required_columns",
    "forbidden_columns_absent",
    "unexpected_columns",
    "pseudonymized__order_id",
    "pseudonymized__customer_unique_id",
    "pseudonymized__seller_key",
    "default_fill__customer_state",
    "default_fill__seller_state",
    "default_fill__order_status",
    "default_fill__payment_type_mode",
    "default_fill__seller_volume_tier",
    "classification_leakage",
    "policy_required_columns_alignment",
    "policy_forbidden_columns_alignment",
    "policy_pseudonymization_alignment",
    "policy_default_fill_alignment",
]


def _compliant_source() -> pd.DataFrame:
    values: dict[str, list[int | str | None]] = {
        column: [1] for column in PUBLISHED_COLUMNS if column != "seller_key"
    }
    values.update(
        {
            "order_id": ["order"],
            "customer_unique_id": ["customer"],
            "seller_id": ["seller"],
            "customer_state": [None],
            "seller_state": [None],
            "order_status": [None],
            "payment_type_mode": [None],
            "seller_volume_tier": [None],
        }
    )
    return pd.DataFrame(values)


def test_privacy_engine_matches_synthetic_4_pass_12_fail_golden() -> None:
    contract = load_privacy_contract()
    policy = load_domain_policy(contract)
    checks = validate_privacy_controls(
        unprotected_published_frame(list(contract["required_columns"])),
        contract,
        policy,
        classification_rows=CLASSIFICATION_ROWS,
    )

    assert [check.check_name for check in checks] == EXPECTED_CHECKS
    assert [check.status for check in checks].count("PASS") == 4
    assert [check.status for check in checks].count("FAIL") == 12
    assert [asdict(check) for check in checks] == expected_privacy_failures()


def test_privacy_engine_keeps_all_16_checks_for_compliant_published_frame() -> None:
    source = _compliant_source()
    published = build_published_dashboard_table(source)
    contract = load_privacy_contract()
    policy = load_domain_policy(contract)

    checks = validate_privacy_controls(
        published,
        contract,
        policy,
        source_df=source,
        classification_rows=CLASSIFICATION_ROWS,
    )

    assert [check.check_name for check in checks] == EXPECTED_CHECKS
    assert [check.status for check in checks] == ["PASS"] * 16
