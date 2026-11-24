from __future__ import annotations

import logging
import os
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.config import DOCS_DIR, PUBLISHED_DASHBOARD_DIR, PUBLISHED_SEMANTIC_DIR
from src.ingest import configure_logging
from src.public_mode import is_public_visitor_mode
from src.utils import ensure_directory

LOGGER = logging.getLogger(__name__)
PUBLISHED_SOURCE_PATH = PUBLISHED_DASHBOARD_DIR / "fact_orders_dashboard.parquet"
LOGISTICS_PATH = PUBLISHED_SEMANTIC_DIR / "logistics_slice.parquet"
SELLER_PATH = PUBLISHED_SEMANTIC_DIR / "seller_slice.parquet"
COHORT_PATH = PUBLISHED_SEMANTIC_DIR / "cohort_slice.parquet"
CATEGORY_PATH = PUBLISHED_SEMANTIC_DIR / "category_slice.parquet"
STATE_PATH = PUBLISHED_SEMANTIC_DIR / "state_performance_slice.parquet"
REPORT_PATH = DOCS_DIR / "semantic_layer.md"


@dataclass(frozen=True)
class SemanticArtifacts:
    logistics_path: Path
    seller_path: Path
    cohort_path: Path
    category_path: Path
    state_path: Path


def load_published_table() -> pd.DataFrame:
    if is_public_visitor_mode():
        # Public visitor profile never reads persisted artifacts directly.
        # The semantic layer must always be derived from an explicitly
        # authorized dataset (path + purpose + sha256 + revocation).
        from src.data_loader import DEFAULT_PUBLIC_DEMO_DATASET, load_dataset

        return load_dataset(DEFAULT_PUBLIC_DEMO_DATASET)

    if PUBLISHED_SOURCE_PATH.exists():
        return pd.read_parquet(PUBLISHED_SOURCE_PATH)

    configured_source = os.getenv("GAP_SEMANTIC_LAYER_SOURCE_PATH", "").strip()
    if configured_source:
        source_path = Path(configured_source)
        if not source_path.exists() or source_path.is_symlink():
            raise FileNotFoundError(
                f"Semantic layer source not found (or symlinked): {source_path}"
            )
        return pd.read_parquet(source_path)

    raise FileNotFoundError(
        f"Camada publicada nao encontrada para expansao semantica: {PUBLISHED_SOURCE_PATH}"
    )


def build_logistics_slice(df: pd.DataFrame) -> pd.DataFrame:
    logistics = (
        df.groupby(
            ["order_year", "order_month", "customer_state", "seller_state"],
            dropna=False,
        )
        .agg(
            total_items=("order_item_id", "count"),
            delayed_rate=("is_delayed", "mean"),
            avg_delivery_time_days=("delivery_time_days", "mean"),
            avg_dispatch_time_days=("seller_dispatch_time_days", "mean"),
            avg_carrier_time_days=("carrier_delivery_time_days", "mean"),
            avg_freight_to_price_ratio=("freight_to_price_ratio", "mean"),
        )
        .reset_index()
    )
    return logistics.sort_values(
        ["order_year", "order_month", "customer_state", "seller_state"]
    ).reset_index(drop=True)


def build_seller_slice(df: pd.DataFrame) -> pd.DataFrame:
    keys = ["seller_key", "seller_state", "seller_volume_tier"]
    seller = (
        df.dropna(subset=["seller_key"])
        .groupby(keys, dropna=False)
        .agg(
            total_items=("order_item_id", "count"),
            seller_order_count=("order_id", "nunique"),
            gross_item_value=(
                "total_item_value",
                lambda amounts: amounts.sum(min_count=1),
            ),
            avg_ticket=("total_item_value", "mean"),
            avg_delivery_time_days=("seller_avg_delivery_days", "max"),
            delay_rate=("seller_delay_rate", "max"),
            avg_review_score=("review_score_mean", "mean"),
        )
        .reset_index()
    )
    return seller.sort_values(["seller_volume_tier", "seller_key"]).reset_index(
        drop=True
    )


def build_cohort_slice(df: pd.DataFrame) -> pd.DataFrame:
    month_column = "purchase_cohort_month"
    offset_column = "cohort_order_month_number"
    keys = [month_column, offset_column]
    cohort_month = pd.to_datetime(df[month_column], format="%Y-%m", errors="coerce")
    offset = pd.to_numeric(df[offset_column], errors="coerce")
    valid = cohort_month.notna() & offset.ge(0) & offset.mod(1).eq(0)
    dates = None
    if "order_purchase_timestamp" in df:
        dates = pd.to_datetime(df["order_purchase_timestamp"], errors="coerce")
        actual_offset = (
            (dates.dt.year - cohort_month.dt.year) * 12
            + dates.dt.month
            - cohort_month.dt.month
        )
        valid &= dates.notna() & actual_offset.eq(offset)
    members = df.loc[valid].dropna(subset=["customer_unique_id", "order_id"])
    months_per_customer = members.groupby("customer_unique_id")[month_column].nunique()
    stable = members["customer_unique_id"].map(months_per_customer).eq(1)
    members = members.loc[stable].assign(
        **{offset_column: offset.loc[members.index].loc[stable]}
    )
    population = members.loc[members[offset_column].eq(0), "customer_unique_id"]
    members = members.loc[members["customer_unique_id"].isin(population)]
    cohort = (
        members.groupby(keys)
        .agg(
            customers=("customer_unique_id", "nunique"),
            orders=("order_id", "nunique"),
            items=("order_item_id", "count"),
            avg_ticket=("total_item_value", "mean"),
            gross_item_value=(
                "total_item_value",
                lambda amounts: amounts.sum(min_count=1),
            ),
            delayed_rate=("is_delayed", "mean"),
        )
        .reset_index()
    )
    cohort["avg_order_ticket"] = cohort["gross_item_value"].div(
        cohort["orders"].where(cohort["orders"].gt(0))
    )
    if dates is not None:
        latest = dates.max()
        first = dates.min()
        acquisition = pd.PeriodIndex(cohort[month_column], freq="M")
        observed = acquisition + cohort[offset_column].to_numpy(dtype="int64")
        cohort["retention_observable"] = (
            pd.notna(latest)
            and pd.notna(first)
            and (observed.start_time.normalize() >= first.normalize())
            & (observed.end_time.normalize() <= latest.normalize())
            & (acquisition.start_time.normalize() >= first.normalize())
        )
    return cohort.sort_values(keys).reset_index(drop=True)


def build_category_slice(df: pd.DataFrame) -> pd.DataFrame:
    category = (
        df.groupby(
            [
                "order_year",
                "order_month",
                "product_category_name_english",
                "payment_type_mode",
            ],
            dropna=False,
        )
        .agg(
            orders=("order_id", "nunique"),
            items=("order_item_id", "count"),
            revenue=("total_item_value", "sum"),
            avg_ticket=("total_item_value", "mean"),
            delayed_rate=("is_delayed", "mean"),
            avg_review_score=("review_score_mean", "mean"),
            avg_freight_to_price_ratio=("freight_to_price_ratio", "mean"),
        )
        .reset_index()
    )
    return category.sort_values(
        [
            "order_year",
            "order_month",
            "product_category_name_english",
            "payment_type_mode",
        ]
    ).reset_index(drop=True)


def build_state_performance_slice(df: pd.DataFrame) -> pd.DataFrame:
    state = (
        df.groupby(["order_year", "order_month", "customer_state"], dropna=False)
        .agg(
            orders=("order_id", "nunique"),
            items=("order_item_id", "count"),
            active_sellers=("seller_key", "nunique"),
            revenue=("total_item_value", "sum"),
            avg_ticket=("total_item_value", "mean"),
            delayed_rate=("is_delayed", "mean"),
            avg_delivery_time_days=("delivery_time_days", "mean"),
            avg_review_score=("review_score_mean", "mean"),
        )
        .reset_index()
    )
    return state.sort_values(
        ["order_year", "order_month", "customer_state"]
    ).reset_index(drop=True)


def save_dataset(df: pd.DataFrame, path: Path) -> None:
    df.to_parquet(path, index=False)
    df.to_csv(path.with_suffix(".csv"), index=False)


def stage_dataset(df: pd.DataFrame, path: Path, temp_dir: Path) -> tuple[Path, Path]:
    token = uuid.uuid4().hex
    parquet_tmp = temp_dir / f"{path.name}.{token}.tmp"
    csv_target = path.with_suffix(".csv")
    csv_tmp = temp_dir / f"{csv_target.name}.{token}.tmp"
    df.to_parquet(parquet_tmp, index=False)
    df.to_csv(csv_tmp, index=False)
    return parquet_tmp, csv_tmp


def commit_staged_dataset(parquet_tmp: Path, csv_tmp: Path, target: Path) -> None:
    parquet_tmp.replace(target)
    csv_tmp.replace(target.with_suffix(".csv"))


def render_report(
    logistics: pd.DataFrame,
    seller: pd.DataFrame,
    cohort: pd.DataFrame,
    category: pd.DataFrame,
    state: pd.DataFrame,
) -> str:
    lines = [
        "# Camada Semantica Expandida",
        "",
        "A camada published passa a expor marts operacionais e executivos para recortes de logistica, seller, cohort, categoria e geografia.",
        "",
        "## Ativos Gerados",
        "",
        f"- `logistics_slice`: **{len(logistics):,}** linhas",
        f"- `seller_slice`: **{len(seller):,}** linhas",
        f"- `cohort_slice`: **{len(cohort):,}** linhas",
        f"- `category_slice`: **{len(category):,}** linhas",
        f"- `state_performance_slice`: **{len(state):,}** linhas",
        "",
        "## Recortes Disponiveis",
        "",
        "- Logistica: tempo medio de entrega, despacho, transporte e peso relativo do frete por UF origem/destino e mes.",
        "- Seller: tier de volume, atraso medio, entrega media, ticket medio e satisfacao por seller pseudonimizado.",
        "- Cohort: comportamento por cohort de compra e maturacao mensal da base de clientes.",
        "- Categoria: receita, ticket, atraso, review e meio de pagamento por categoria e mes.",
        "- Geografia executiva: receita, sellers ativos, atraso e satisfacao por UF e mes.",
        "",
    ]
    return "\n".join(lines)


def _resolve_targets(
    output_dir: Path | None,
    docs_dir: Path | None,
) -> tuple[Path, Path, Path, Path, Path, Path, Path, Path]:
    if output_dir is None and docs_dir is None:
        return (
            PUBLISHED_SEMANTIC_DIR,
            DOCS_DIR,
            LOGISTICS_PATH,
            SELLER_PATH,
            COHORT_PATH,
            CATEGORY_PATH,
            STATE_PATH,
            REPORT_PATH,
        )

    resolved_output = output_dir or PUBLISHED_SEMANTIC_DIR
    resolved_docs = docs_dir or DOCS_DIR
    return (
        resolved_output,
        resolved_docs,
        resolved_output / "logistics_slice.parquet",
        resolved_output / "seller_slice.parquet",
        resolved_output / "cohort_slice.parquet",
        resolved_output / "category_slice.parquet",
        resolved_output / "state_performance_slice.parquet",
        resolved_docs / "semantic_layer.md",
    )


def run_semantic_layer(
    *,
    output_dir: Path | None = None,
    docs_dir: Path | None = None,
) -> SemanticArtifacts:
    (
        resolved_output,
        resolved_docs,
        logistics_path,
        seller_path,
        cohort_path,
        category_path,
        state_path,
        report_path,
    ) = _resolve_targets(output_dir, docs_dir)

    ensure_directory(resolved_output)
    ensure_directory(resolved_docs)

    published = load_published_table()
    logistics = build_logistics_slice(published)
    seller = build_seller_slice(published)
    cohort = build_cohort_slice(published)
    category = build_category_slice(published)
    state = build_state_performance_slice(published)

    with tempfile.TemporaryDirectory(
        prefix=".tmp_semantic_layer_",
        dir=resolved_output,
    ) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        staged: list[tuple[Path, Path, Path]] = []
        for df, target in (
            (logistics, logistics_path),
            (seller, seller_path),
            (cohort, cohort_path),
            (category, category_path),
            (state, state_path),
        ):
            parquet_tmp, csv_tmp = stage_dataset(df, target, temp_dir)
            staged.append((parquet_tmp, csv_tmp, target))

        for parquet_tmp, csv_tmp, target in staged:
            commit_staged_dataset(parquet_tmp, csv_tmp, target)

        report_path.write_text(
            render_report(logistics, seller, cohort, category, state),
            encoding="utf-8",
        )

    LOGGER.info("Camada semantica expandida materializada em %s", resolved_output)
    return SemanticArtifacts(
        logistics_path=logistics_path,
        seller_path=seller_path,
        cohort_path=cohort_path,
        category_path=category_path,
        state_path=state_path,
    )


if __name__ == "__main__":
    configure_logging()
    run_semantic_layer()
