from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd
import streamlit as st

from app.i18n import Locale, t
from src.data_loader import (
    DEFAULT_PUBLIC_DEMO_DATASET,
    DEFAULT_SAMPLE_DATASET,
    load_dataset,
)
from src.data_quality import generate_data_quality_table as generate_data_quality_table
from src.data_quality import run_data_quality_checks
from src.governance_types import DataQualityResult, PrivacyRiskResult
from src.lgpd_classifier import classify_dataframe_columns
from src.public_distribution_authorization import public_demo_authorization_complete
from src.public_mode import is_public_visitor_mode
from src.publication_gate import (
    OperationalPublicationGateDecision,
    evaluate_operational_publication_gate,
)
from src.risk_scoring import calculate_privacy_risk_score

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PUBLISHED_DATASET = (
    PROJECT_ROOT / "data/published/dashboard/fact_orders_dashboard.csv"
)


@dataclass(frozen=True)
class GovernanceAppContext:
    df: pd.DataFrame
    classification_df: pd.DataFrame
    quality_results: DataQualityResult
    quality_table: pd.DataFrame
    risk_result: PrivacyRiskResult
    report_paths: dict[str, Path]
    uses_persisted_governance: bool = False
    public_distribution_gate: OperationalPublicationGateDecision | None = None


def _render_data_freshness_sidebar(locale: Locale) -> None:
    is_en = locale == "en-US"
    if DEFAULT_PUBLISHED_DATASET.exists():
        import time

        mtime = DEFAULT_PUBLISHED_DATASET.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600
        if age_hours < 1:
            age_str = "< 1h"
        elif age_hours < 24:
            age_str = (
                f"{int(age_hours)}h atrás" if not is_en else f"{int(age_hours)}h ago"
            )
        else:
            days = int(age_hours / 24)
            age_str = f"{days}d atrás" if not is_en else f"{days}d ago"
        label = "Dados publicados:" if not is_en else "Published data:"
        st.sidebar.caption(f"{label} **{age_str}**")
    else:
        st.sidebar.caption(
            "Pipeline não executado ainda." if not is_en else "Pipeline not run yet."
        )


def _load_platform_dataframe(path: Path) -> pd.DataFrame:
    dataframe = load_dataset(path)
    dataframe.attrs["uses_persisted_governance"] = (
        path.resolve() == DEFAULT_PUBLISHED_DATASET.resolve()
    )
    dataframe.attrs["dataset_name"] = path.stem
    return dataframe


def load_input_dataframe(locale: Locale) -> pd.DataFrame:
    if is_public_visitor_mode():
        # Public mode never routes to historical data or arbitrary uploads.
        return _load_platform_dataframe(DEFAULT_PUBLIC_DEMO_DATASET)
    st.sidebar.header(t("data_source_header", locale))
    uploaded_file = st.sidebar.file_uploader(
        t("upload_label", locale), type=["csv", "parquet"]
    )
    use_sample = st.sidebar.toggle(t("use_sample_toggle", locale), value=True)
    _render_data_freshness_sidebar(locale)

    if uploaded_file is not None:
        suffix = Path(uploaded_file.name).suffix.lower()
        if suffix == ".parquet":
            dataframe = pd.read_parquet(uploaded_file)
        else:
            dataframe = pd.read_csv(uploaded_file)
        dataframe.attrs["uses_persisted_governance"] = False
        dataframe.attrs["dataset_name"] = Path(uploaded_file.name).stem
        return dataframe

    if use_sample:
        if DEFAULT_PUBLISHED_DATASET.exists():
            return _load_platform_dataframe(DEFAULT_PUBLISHED_DATASET)
        return _load_platform_dataframe(DEFAULT_SAMPLE_DATASET)
    if DEFAULT_PUBLISHED_DATASET.exists():
        return _load_platform_dataframe(DEFAULT_PUBLISHED_DATASET)
    return _load_platform_dataframe(DEFAULT_SAMPLE_DATASET)


@st.cache_data(show_spinner=False)
def _build_context_from_dataframe(
    df: pd.DataFrame,
    docs_dir: str | Path = "docs",
    *,
    uses_persisted_governance: bool = False,
) -> GovernanceAppContext:
    classification_df = classify_dataframe_columns(df)
    dataset_name = (
        "fact_orders_dashboard"
        if uses_persisted_governance
        else df.attrs.get("quality_dataset")
    )
    quality_results = (
        run_data_quality_checks(df, dataset_name=dataset_name)
        if dataset_name is not None
        else run_data_quality_checks(df)
    )
    quality_table = pd.DataFrame(quality_results["checks"])
    risk_result = calculate_privacy_risk_score(classification_df, total_rows=len(df))
    docs_path = Path(docs_dir)
    report_paths = (
        {
            "data_dictionary": docs_path / "reports/data_dictionary.md",
            "data_quality_report": docs_path / "reports/data_quality_report.md",
            "lgpd_controls": docs_path / "governance/lgpd_controls.md",
            "lgpd_ripd_sample": docs_path / "governance/lgpd_ripd_sample.md",
        }
        if uses_persisted_governance
        else {}
    )
    return GovernanceAppContext(
        df=df,
        classification_df=classification_df,
        quality_results=quality_results,
        quality_table=quality_table,
        risk_result=risk_result,
        report_paths=report_paths,
        uses_persisted_governance=uses_persisted_governance,
    )


def build_context(
    locale: Locale, *, docs_dir: str | Path = "docs"
) -> GovernanceAppContext:
    df = load_input_dataframe(locale)
    context = _build_context_from_dataframe(
        df,
        docs_dir=docs_dir,
        uses_persisted_governance=bool(
            df.attrs.get("uses_persisted_governance", False)
        ),
    )
    public_gate = None
    if context.quality_results.get("dataset_name") == "fact_orders_dashboard":
        quality_results = context.quality_results
        checks = quality_results["checks"]
        public_gate = evaluate_operational_publication_gate(
            total_checks=len(checks),
            pass_checks=sum(check["status"] == "PASS" for check in checks),
            warn_checks=0,
            fail_checks=quality_results["failed_checks_count"],
            critical_failures=sum(
                check["status"] == "FAIL" and check["severity"] == "critical"
                for check in checks
            ),
            public_authorization_complete=public_demo_authorization_complete(
                PROJECT_ROOT
            ),
        )
    # Authorization is intentionally rechecked outside the cached profiler so
    # revocation or changed artifact bytes cannot retain a cached public grant.
    context = replace(context, public_distribution_gate=public_gate)
    if (
        context.public_distribution_gate is not None
        and context.public_distribution_gate.decision == "BLOCKED"
    ):
        st.sidebar.warning(
            "Public distribution: BLOCKED. " + context.public_distribution_gate.reason
        )
    return context
