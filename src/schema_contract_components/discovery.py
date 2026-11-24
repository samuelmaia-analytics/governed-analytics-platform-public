from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def load_contract(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_contract_paths(contracts_dir: Path) -> list[Path]:
    return sorted(contracts_dir.glob("*/*.contract.json"))


def normalize_csv_dates(
    dataframe: pd.DataFrame, contract: dict[str, Any]
) -> pd.DataFrame:
    for column, expected_type in contract.get("columns", {}).items():
        if column in dataframe and expected_type in {"datetime", "date_like"}:
            try:
                dataframe[column] = pd.to_datetime(
                    dataframe[column], format="mixed", errors="raise"
                )
            except (ValueError, TypeError):
                # Preserve malformed values so the existing type check fails.
                pass
    return dataframe


def load_dataset(contract: dict[str, Any], *, root_dir: Path) -> pd.DataFrame:
    dataset_path = root_dir / str(contract["path"])
    if dataset_path.suffix == ".parquet":
        return pd.read_parquet(dataset_path)
    if dataset_path.suffix == ".csv":
        return normalize_csv_dates(pd.read_csv(dataset_path), contract)
    raise ValueError(f"Formato nao suportado no contrato: {dataset_path}")
