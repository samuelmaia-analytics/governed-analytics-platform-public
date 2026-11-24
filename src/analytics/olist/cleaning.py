"""Column normalization and source-table cleaning for Olist analytics."""

from __future__ import annotations

import re

import pandas as pd

from src.analytics.olist.quarantine import RejectRows, exclude_rows


def to_snake_case(value: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z]+", "_", value.strip())
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_").lower()


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={column: to_snake_case(column) for column in df.columns})


def convert_datetime_columns(df: pd.DataFrame) -> pd.DataFrame:
    converted = df.copy()
    for column in converted.columns:
        if "date" in column or "timestamp" in column or column.endswith("_at"):
            converted[column] = pd.to_datetime(converted[column], errors="coerce")
    return converted


def deduplicate(df: pd.DataFrame, subset: list[str] | None = None) -> pd.DataFrame:
    return df.drop_duplicates(subset=subset, keep="first").copy()


def _clean_keys(
    frame: pd.DataFrame,
    required: list[str],
    duplicate_key: list[str] | None,
    reject: RejectRows | None,
    *,
    convert_dates: bool = False,
) -> pd.DataFrame:
    frame = exclude_rows(
        frame, frame.duplicated(subset=duplicate_key), "duplicate", reject
    )
    if convert_dates:
        frame = convert_datetime_columns(frame)
    return exclude_rows(
        frame, frame[required].isna().any(axis=1), "missing_required_key", reject
    )


def clean_orders(
    orders: pd.DataFrame, *, reject: RejectRows | None = None
) -> pd.DataFrame:
    return _clean_keys(
        orders, ["order_id", "customer_id"], ["order_id"], reject, convert_dates=True
    )


def clean_order_items(
    order_items: pd.DataFrame, *, reject: RejectRows | None = None
) -> pd.DataFrame:
    order_items = _clean_keys(
        order_items,
        ["order_id", "order_item_id", "product_id", "seller_id"],
        None,
        reject,
        convert_dates=True,
    )
    order_items = exclude_rows(
        order_items, order_items["price"].fillna(0) < 0, "negative_price", reject
    )
    order_items = exclude_rows(
        order_items,
        order_items["freight_value"].fillna(0) < 0,
        "negative_freight",
        reject,
    )
    return order_items


def clean_customers(
    customers: pd.DataFrame, *, reject: RejectRows | None = None
) -> pd.DataFrame:
    return _clean_keys(customers, ["customer_id"], ["customer_id"], reject)


def clean_products(
    products: pd.DataFrame, *, reject: RejectRows | None = None
) -> pd.DataFrame:
    return _clean_keys(products, ["product_id"], ["product_id"], reject)


def clean_sellers(
    sellers: pd.DataFrame, *, reject: RejectRows | None = None
) -> pd.DataFrame:
    return _clean_keys(sellers, ["seller_id"], ["seller_id"], reject)


def clean_translation(
    translation: pd.DataFrame, *, reject: RejectRows | None = None
) -> pd.DataFrame:
    return _clean_keys(
        translation, ["product_category_name"], ["product_category_name"], reject
    )
