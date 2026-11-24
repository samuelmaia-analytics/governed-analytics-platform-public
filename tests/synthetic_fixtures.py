"""Deterministic test scenarios authored from contracts without historical data."""

from __future__ import annotations

import pandas as pd


def valid_orders() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "order_id": [f"scenario-order-{number:04d}" for number in range(1, 4)],
            "customer_id": [
                f"scenario-customer-{number:04d}" for number in range(1, 4)
            ],
            "customer_email": [
                f"scenario-{number}@example.invalid" for number in range(1, 4)
            ],
            "order_status": ["delivered", "shipped", "processing"],
            "order_date": pd.to_datetime(["2001-01-01", "2001-01-02", "2001-01-03"]),
            "revenue": [25.0, 50.0, 75.0],
        }
    )


def orders_missing_customer_id() -> pd.DataFrame:
    frame = valid_orders()
    frame.loc[1, "customer_id"] = None
    return frame


def orders_missing_order_column() -> pd.DataFrame:
    return valid_orders().drop(columns="order_id")


def orders_with_high_privacy_risk() -> pd.DataFrame:
    frame = valid_orders()
    frame["health_status"] = "synthetic-health-scenario"
    frame["customer_document"] = "SYNTHETIC-NONVALID-DOCUMENT"
    frame["customer_phone"] = "SYNTHETIC-NONDIALABLE-CONTACT"
    frame["customer_email_backup"] = "scenario-backup@example.invalid"
    return frame


def unprotected_published_frame(required_columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame(
        {column: [pd.NA] for column in required_columns if column != "seller_key"}
    )
    frame["order_id"] = "unprotected-scenario-order"
    frame["customer_unique_id"] = "unprotected-scenario-customer"
    frame["customer_city"] = "synthetic-locality"
    frame["customer_id"] = "synthetic-source-customer"
    frame["product_id"] = "synthetic-source-product"
    frame["seller_id"] = "synthetic-source-seller"
    return frame


def expected_privacy_failures() -> list[dict[str, str]]:
    """Independent oracle specified by the 16 privacy-check contracts.

    This function neither loads old CSVs nor calls the privacy validator.
    Its expectation strings describe schema and controls, without data rows.
    """
    records = [
        ("required_columns", "FAIL", "Ausentes: ['seller_key']"),
        (
            "forbidden_columns_absent",
            "FAIL",
            "Presentes indevidas: ['customer_city', 'customer_id', 'product_id', 'seller_id']",
        ),
        (
            "unexpected_columns",
            "FAIL",
            "Inesperadas: ['customer_city', 'customer_id', 'product_id', 'seller_id']",
        ),
        ("pseudonymized__order_id", "FAIL", "Prefixo esperado: `order_id_`"),
        (
            "pseudonymized__customer_unique_id",
            "FAIL",
            "Prefixo esperado: `customer_unique_id_`",
        ),
        ("pseudonymized__seller_key", "FAIL", "Coluna obrigatória ausente."),
    ]
    for column in (
        "customer_state",
        "seller_state",
        "order_status",
        "payment_type_mode",
        "seller_volume_tier",
    ):
        records.append(
            (
                f"default_fill__{column}",
                "FAIL",
                "nulls=1 | default_observado=False | default_aplicado=False",
            )
        )
    records.extend(
        [
            (
                "classification_leakage",
                "FAIL",
                "Colunas sensíveis expostas: ['customer_city', 'customer_id', 'seller_id']",
            ),
            (
                "policy_required_columns_alignment",
                "PASS",
                "Contrato e política LGPD devem ter as mesmas colunas obrigatórias.",
            ),
            (
                "policy_forbidden_columns_alignment",
                "PASS",
                "Contrato e política LGPD devem ter as mesmas colunas proibidas.",
            ),
            (
                "policy_pseudonymization_alignment",
                "PASS",
                "Contrato e política LGPD devem ter o mesmo mapeamento de pseudonimização.",
            ),
            (
                "policy_default_fill_alignment",
                "PASS",
                "Contrato e política LGPD devem ter os mesmos defaults de preenchimento.",
            ),
        ]
    )
    return [
        {"check_name": name, "status": status, "details": details}
        for name, status, details in records
    ]
