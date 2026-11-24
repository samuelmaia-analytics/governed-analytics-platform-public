"""Shared definitions for audited dashboard views."""

from __future__ import annotations

import pandas as pd

ITEM_KEY = ["order_id", "order_item_id"]
SELLER_GROUP = ["seller_key", "seller_state", "seller_volume_tier"]
COHORT_KEY = ["purchase_cohort_month", "cohort_order_month_number"]


def valid_item_grain(df: pd.DataFrame) -> bool:
    return (
        set(ITEM_KEY).issubset(df.columns)
        and not df[ITEM_KEY].isna().any(axis=None)
        and not df.duplicated(ITEM_KEY).any()
    )


def cohort_retention(frame: pd.DataFrame) -> pd.DataFrame:
    """Join the original cohort population without multiplying cells."""
    cohort = frame.copy()
    month, offset = COHORT_KEY
    cohort[offset] = pd.to_numeric(cohort[offset], errors="coerce")
    cohort["customers"] = pd.to_numeric(cohort["customers"], errors="coerce")
    valid = (
        cohort[month].notna()
        & cohort[offset].ge(0)
        & cohort[offset].mod(1).eq(0)
        & ~cohort.duplicated(COHORT_KEY, keep=False)
    )
    cohort = cohort.loc[valid]
    baseline = cohort.loc[cohort[offset].eq(0), [month, "customers"]].rename(
        columns={"customers": "baseline_customers"}
    )
    retention = cohort.merge(baseline, on=month, how="left", validate="many_to_one")
    population = retention["baseline_customers"]
    active = retention["customers"]
    observable = population.gt(0) & active.ge(0) & active.le(population)
    if "retention_observable" in retention:
        observable &= retention["retention_observable"].eq(True)
    retention["retention_rate"] = active.div(population.where(observable)).mul(100)
    return retention


def filtered_seller_order_count(fact: pd.DataFrame, groups: pd.DataFrame) -> int:
    matching = fact.merge(groups[SELLER_GROUP], on=SELLER_GROUP, validate="many_to_one")
    return int(matching["order_id"].nunique())
