from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

from src.public_distribution_authorization import (
    public_distribution_artifact_authorized,
)
from src.public_mode import is_public_visitor_mode
from src.schema_contract_components.discovery import load_contract, normalize_csv_dates

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE_DATASET = PROJECT_ROOT / "data/samples/sample_governance_dataset.csv"
DEFAULT_PUBLIC_DEMO_DATASET = (
    PROJECT_ROOT / "data/samples/gap_public_demo_synthetic_v1.parquet"
)


def load_dataset(dataset_path: str | Path | None = None) -> pd.DataFrame:
    """Load a dataset from a provided path or from the project sample dataset."""
    public_mode = is_public_visitor_mode()
    source_path = (
        Path(dataset_path)
        if dataset_path
        else (DEFAULT_PUBLIC_DEMO_DATASET if public_mode else DEFAULT_SAMPLE_DATASET)
    )
    if not source_path.exists():
        if (
            source_path == DEFAULT_SAMPLE_DATASET
            and not is_public_visitor_mode()
        ):
            return pd.DataFrame(
                {
                    "order_id": ["demo-order-1", "demo-order-2"],
                    "customer_id": ["demo-customer-1", "demo-customer-2"],
                    "price": [100.0, 125.0],
                    "order_purchase_timestamp": pd.to_datetime(
                        ["2024-01-01", "2024-01-02"]
                    ),
                }
            )
        raise FileNotFoundError(f"Dataset not found: {source_path}")
    root = PROJECT_ROOT
    source: Path | BytesIO = source_path
    if is_public_visitor_mode():
        name = "data/samples/gap_public_demo_synthetic_v1.parquet"
        if source_path.resolve() != root / name or source_path.is_symlink():
            raise PermissionError("Dataset is outside the public demo scope.")
        content = source_path.read_bytes()
        if not public_distribution_artifact_authorized(
            root, name, "synthetic_demo_preview", content
        ):
            raise PermissionError(
                "Dataset has no current public distribution authorization."
            )
        source = BytesIO(content)
    if source_path.suffix.lower() == ".parquet":
        result = pd.read_parquet(source)
    else:
        result = pd.read_csv(source)
        if (
            source_path.resolve()
            == root / "data/published/dashboard/fact_orders_dashboard.csv"
        ):
            contract = load_contract(
                root / "contracts/published/fact_orders_dashboard.contract.json"
            )
            result = normalize_csv_dates(result, contract)
    if source_path.resolve() in {
        root / "data/published/dashboard/fact_orders_dashboard.csv",
        root / "data/published/dashboard/fact_orders_dashboard.parquet",
        root / "data/samples/gap_public_demo_synthetic_v1.parquet",
    }:
        # Technical contract selection grants no public delivery authorization.
        result.attrs["quality_dataset"] = "fact_orders_dashboard"
    return result


def infer_dataset_name(dataset_path: str | Path | None = None) -> str:
    source_path = Path(dataset_path) if dataset_path else DEFAULT_SAMPLE_DATASET
    return source_path.stem
