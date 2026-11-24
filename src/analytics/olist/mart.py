"""Construction of the canonical Olist analytical mart."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial

import pandas as pd

from src.analytics.olist.aggregations import build_payments_agg, build_reviews_agg
from src.analytics.olist.cleaning import (
    clean_customers,
    clean_order_items,
    clean_orders,
    clean_products,
    clean_sellers,
    clean_translation,
    convert_datetime_columns,
)
from src.analytics.olist.quarantine import RejectionJournal
from src.analytics.olist.transformations import (
    derive_columns,
    remove_obvious_inconsistencies,
    select_output_columns,
)

ReadTableFn = Callable[[str], pd.DataFrame]
ValidateNotEmptyFn = Callable[[pd.DataFrame, str], None]


def build_fact_orders_enriched(
    *,
    read_table_fn: ReadTableFn,
    validate_not_empty_fn: ValidateNotEmptyFn,
    logger: logging.Logger,
    quarantine: RejectionJournal | None = None,
) -> pd.DataFrame:
    def clean(dataset: str, cleaner: Callable[..., pd.DataFrame]) -> pd.DataFrame:
        reject = (
            partial(quarantine.capture, dataset) if quarantine is not None else None
        )
        return cleaner(read_table_fn(dataset), reject=reject)

    orders = clean("olist_orders_dataset.csv", clean_orders)
    order_items = clean("olist_order_items_dataset.csv", clean_order_items)
    customers = clean("olist_customers_dataset.csv", clean_customers)
    products = clean("olist_products_dataset.csv", clean_products)
    sellers = clean("olist_sellers_dataset.csv", clean_sellers)
    payments = build_payments_agg(
        convert_datetime_columns(read_table_fn("olist_order_payments_dataset.csv"))
    )
    reviews = build_reviews_agg(
        convert_datetime_columns(read_table_fn("olist_order_reviews_dataset.csv"))
    )
    translation = clean("product_category_name_translation.csv", clean_translation)

    fact_table = order_items.merge(
        orders, on="order_id", how="left", validate="many_to_one"
    )
    fact_table = fact_table.merge(
        customers, on="customer_id", how="left", validate="many_to_one"
    )
    fact_table = fact_table.merge(
        products, on="product_id", how="left", validate="many_to_one"
    )
    fact_table = fact_table.merge(
        sellers, on="seller_id", how="left", validate="many_to_one"
    )
    fact_table = fact_table.merge(
        payments, on="order_id", how="left", validate="many_to_one"
    )
    fact_table = fact_table.merge(
        reviews, on="order_id", how="left", validate="many_to_one"
    )
    fact_table = fact_table.merge(
        translation,
        on="product_category_name",
        how="left",
        validate="many_to_one",
    )

    fact_table = derive_columns(fact_table)
    reject = (
        partial(quarantine.capture, "fact_orders_enriched")
        if quarantine is not None
        else None
    )
    fact_table = remove_obvious_inconsistencies(fact_table, reject=reject)
    if quarantine is not None:
        quarantine.persist()
    fact_table = select_output_columns(fact_table)

    validate_not_empty_fn(fact_table, "fact_orders_enriched")
    if len(fact_table) <= 100_000:
        raise ValueError(
            f"fact_orders_enriched precisa ter mais de 100.000 registros, mas possui {len(fact_table)}."
        )

    logger.info("Tabela analítica final pronta | shape=(%s, %s)", *fact_table.shape)
    return fact_table
