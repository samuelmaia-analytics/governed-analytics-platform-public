from __future__ import annotations

# ruff: noqa: E402, I001

import sys
from pathlib import Path

import streamlit as st
from streamlit.navigation.page import StreamlitPage

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.context import GovernanceAppContext, build_context, configure_public_profile  # noqa: E402
from app.components.ui import inject_base_styles  # noqa: E402
from app.i18n import build_locale_selector  # noqa: E402
from app.pages.about import render_about  # noqa: E402
from app.pages.cohort_retention import render_cohort_retention  # noqa: E402
from app.pages.data_catalog import render_data_catalog  # noqa: E402
from app.pages.data_quality import render_data_quality  # noqa: E402
from app.pages.eda import render_eda  # noqa: E402
from app.pages.executive_overview import (  # noqa: E402
    render_executive_hero,
    render_executive_overview,
    render_governed_flow,
)
from app.pages.genai_insights import render_genai_insights  # noqa: E402
from app.pages.governance_assistant import render_governance_assistant  # noqa: E402
from app.pages.governance_control_center import (  # noqa: E402
    render_governance_control_center,
)
from app.pages.governance_report import render_governance_report  # noqa: E402
from app.pages.lgpd_privacy_risk import render_lgpd_privacy_risk  # noqa: E402
from app.pages.n8n_automation import render_n8n_automation  # noqa: E402
from app.pages.public_integrations import (  # noqa: E402
    render_public_automation,
    render_public_snowflake,
)
from app.pages.publication_governance import (  # noqa: E402
    render_publication_governance,
)
from app.pages.revenue_analytics import render_revenue_analytics  # noqa: E402
from app.pages.seller_performance import render_seller_performance  # noqa: E402
from app.pages.snowflake_explorer import render_snowflake_explorer  # noqa: E402
from src.duckdb_engine import get_duckdb_version  # noqa: E402
from src.public_mode import is_public_visitor_mode  # noqa: E402

st.set_page_config(
    page_title="Governed Analytics Platform",
    page_icon=":material/policy:",
    layout="wide",
)


def _render_executive_page(
    context: GovernanceAppContext,
    locale: str,
    business_page: StreamlitPage | None = None,
    governance_page: StreamlitPage | None = None,
    quick_pages: dict[str, StreamlitPage] | None = None,
) -> None:
    render_executive_overview(
        context.df,
        context.classification_df,
        context.risk_result,
        context.quality_results,
        locale,
        business_page=business_page,
        governance_page=governance_page,
        quick_pages=quick_pages,
        duckdb_version=get_duckdb_version(),
        uses_persisted_governance=context.uses_persisted_governance,
        public_gate=context.public_distribution_gate,
    )


def _render_catalog_page(context: GovernanceAppContext, locale: str) -> None:
    render_data_catalog(context.df, context.classification_df, locale)


def _render_lgpd_page(context: GovernanceAppContext, locale: str) -> None:
    render_lgpd_privacy_risk(
        context.df, context.classification_df, context.risk_result, locale
    )


def _render_quality_page(context: GovernanceAppContext, locale: str) -> None:
    render_data_quality(context.quality_results, context.quality_table, locale)


def _render_eda_page(context: GovernanceAppContext, locale: str) -> None:
    render_eda(context.df, locale)


def _render_report_page(context: GovernanceAppContext, locale: str) -> None:
    render_governance_report(context.report_paths, locale)


def _render_revenue_page(context: GovernanceAppContext, locale: str) -> None:
    render_revenue_analytics(context.df, locale)


def _render_seller_performance_page(
    _context: GovernanceAppContext, locale: str
) -> None:
    render_seller_performance(locale, df=_context.df)


def _render_cohort_retention_page(_context: GovernanceAppContext, locale: str) -> None:
    render_cohort_retention(locale, df=_context.df)


def _render_genai_page(_context: GovernanceAppContext | None, locale: str) -> None:
    render_genai_insights(locale)


def _render_assistant_page(_context: GovernanceAppContext | None, locale: str) -> None:
    render_governance_assistant(locale)


def _render_control_center_page(context: GovernanceAppContext, locale: str) -> None:
    render_governance_control_center(
        context.df,
        context.classification_df,
        context.risk_result,
        context.quality_results,
        locale,
    )


def _render_snowflake_page(_context: GovernanceAppContext | None, locale: str) -> None:
    if is_public_visitor_mode():
        render_public_snowflake(locale)
        return
    render_snowflake_explorer(locale)


def _render_n8n_automation_page(
    _context: GovernanceAppContext | None, locale: str
) -> None:
    if is_public_visitor_mode():
        render_public_automation(locale)
        return
    render_n8n_automation()


def _render_publication_governance_page(
    context: GovernanceAppContext | None, locale: str
) -> None:
    if is_public_visitor_mode():
        render_publication_governance(
            public_gate=context.public_distribution_gate
            if context is not None
            else None,
            locale=locale,
        )
        return
    render_publication_governance()


def _render_dataset_required(locale: str, *, title: str | None = None) -> None:
    is_en = locale == "en-US"
    if title is not None:
        st.title(title)
    st.warning(
        "Sample unavailable for public viewing."
        if is_en
        else "Amostra indisponível para visualização pública."
    )
    st.write(
        "Explore engineering and governance through the other pages in the menu."
        if is_en
        else "Explore a engenharia e a governança pelas outras páginas do menu."
    )


def _render_overview_without_data(locale: str) -> None:
    render_executive_hero(locale, public_mode=True)
    _render_dataset_required(locale)
    render_governed_flow(locale)


def _visitor_report_paths() -> dict[str, Path]:
    root = Path(__file__).resolve().parents[1]
    return {
        "public_readme": root / "docs/governance/public_readme.md",
        "public_scope": root / "docs/governance/public_scope.md",
        "local_data_lake": root / "docs/architecture/local_data_lake.md",
        "semantic_layer": root / "docs/architecture/semantic_layer.md",
        "data_contracts": root / "docs/data_contracts.md",
    }


def _semantic_slices_ready() -> bool:
    if is_public_visitor_mode():
        return False

    root = Path(__file__).resolve().parents[1]
    required = [
        root / "data/published/semantic/seller_slice.csv",
        root / "data/published/semantic/cohort_slice.csv",
        root / "data/published/semantic/category_slice.csv",
    ]
    return all(path.exists() for path in required)


def _ensure_semantic_slices(locale: str) -> None:
    if _semantic_slices_ready():
        return

    is_en = locale == "en-US"
    spinner = (
        "Materializing semantic slices..."
        if is_en
        else "Materializando slices sem\u00e2nticos..."
    )

    with st.spinner(spinner):
        try:
            from src.semantic_layer import run_semantic_layer

            run_semantic_layer()
        except Exception as exc:  # pragma: no cover
            st.sidebar.warning(
                "Semantic slices unavailable."
                if is_en
                else "Slices sem\u00e2nticos indispon\u00edveis."
            )
            st.sidebar.caption(str(exc))


def main() -> None:
    configure_public_profile()
    locale = build_locale_selector()
    inject_base_styles()

    public_mode = is_public_visitor_mode()
    context: GovernanceAppContext | None

    try:
        context = build_context(locale)
    except (FileNotFoundError, PermissionError):
        if not public_mode:
            raise
        context = None
        st.sidebar.warning(
            "Public visitor profile: dataset blocked."
            if locale == "en-US"
            else "Perfil p\u00fablico: dataset bloqueado."
        )

    if (not public_mode) and context is not None:
        _ensure_semantic_slices(locale)

    is_en = locale == "en-US"

    revenue_page = st.Page(
        lambda: (
            _render_revenue_page(context, locale)
            if context is not None
            else _render_dataset_required(
                locale,
                title=("Business KPIs" if is_en else "Indicadores anal\u00edticos"),
            )
        ),
        title=("Business KPIs" if is_en else "Indicadores anal\u00edticos"),
        icon=":material/paid:",
        url_path="revenue-analytics",
    )
    publication_page = st.Page(
        lambda: _render_publication_governance_page(
            context if context is not None else None, locale
        ),
        title=("Publication Gate" if is_en else "Publication Gate"),
        icon=":material/account_tree:",
        url_path="publication-governance",
    )
    overview_page = st.Page(
        lambda: (
            _render_executive_page(
                context,
                locale,
                business_page=revenue_page,
                governance_page=publication_page,
                quick_pages={
                    "data_quality": quality_page,
                    "data_catalog": catalog_page,
                    "lgpd_privacy": privacy_page,
                    "control_center": control_center_page,
                },
            )
            if context is not None
            else _render_overview_without_data(locale)
        ),
        title="Overview" if is_en else "Visão geral",
        icon=":material/dashboard:",
        url_path="executive-overview",
    )
    privacy_page = st.Page(
        lambda: (
            _render_lgpd_page(context, locale)
            if context is not None
            else _render_dataset_required(
                locale,
                title=("LGPD & Privacy" if is_en else "LGPD e Privacidade"),
            )
        ),
        title=("LGPD & Privacy" if is_en else "LGPD e Privacidade"),
        icon=":material/policy:",
        url_path="lgpd-privacy-risk",
    )
    quality_page = st.Page(
        lambda: (
            _render_quality_page(context, locale)
            if context is not None
            else _render_dataset_required(
                locale,
                title=("Data Quality" if is_en else "Data Quality"),
            )
        ),
        title=("Data Quality" if is_en else "Data Quality"),
        icon=":material/check_circle:",
        url_path="data-quality",
    )
    seller_page = st.Page(
        lambda: (
            _render_seller_performance_page(context, locale)
            if context is not None
            else _render_dataset_required(
                locale,
                title=("Seller Performance" if is_en else "Seller Performance"),
            )
        ),
        title=("Seller Performance" if is_en else "Desempenho de sellers"),
        icon=":material/storefront:",
        url_path="seller-performance",
    )
    cohort_page = st.Page(
        lambda: (
            _render_cohort_retention_page(context, locale)
            if context is not None
            else _render_dataset_required(
                locale,
                title=("Cohort Retention" if is_en else "Cohort Retention"),
            )
        ),
        title=("Cohort Retention" if is_en else "Retenção de clientes"),
        icon=":material/grid_view:",
        url_path="cohort-retention",
    )
    catalog_page = st.Page(
        lambda: (
            _render_catalog_page(context, locale)
            if context is not None
            else _render_dataset_required(
                locale,
                title=(
                    "Data Contracts & Catalog" if is_en else "Contratos e Cat\u00e1logo"
                ),
            )
        ),
        title=("Data Contracts & Catalog" if is_en else "Contratos e Cat\u00e1logo"),
        icon=":material/table_view:",
        url_path="data-catalog",
    )
    eda_page = st.Page(
        lambda: (
            _render_eda_page(context, locale)
            if context is not None
            else _render_dataset_required(
                locale,
                title=(
                    "Exploratory Analysis"
                    if is_en
                    else "An\u00e1lise Explorat\u00f3ria"
                ),
            )
        ),
        title=("Exploratory Analysis" if is_en else "An\u00e1lise Explorat\u00f3ria"),
        icon=":material/monitoring:",
        url_path="technical-analysis",
    )
    evidence_page = st.Page(
        lambda: (
            _render_report_page(context, locale)
            if context is not None and not public_mode
            else render_governance_report(_visitor_report_paths(), locale)
        ),
        title=(
            "Evidence & Traceability" if is_en else "Evid\u00eancias e rastreabilidade"
        ),
        icon=":material/description:",
        url_path="governance-report",
    )
    control_center_page = st.Page(
        lambda: (
            _render_control_center_page(context, locale)
            if context is not None
            else _render_dataset_required(
                locale,
                title=("Control Center" if is_en else "Central de Controles"),
            )
        ),
        title=("Control Center" if is_en else "Central de Controles"),
        icon=":material/admin_panel_settings:",
        url_path="governance-control-center",
    )
    n8n_page = st.Page(
        lambda: _render_n8n_automation_page(
            context if context is not None else None, locale
        ),
        title=("n8n Automation" if is_en else "n8n Automation"),
        icon=":material/account_tree:",
        url_path="n8n-automation",
    )
    genai_page = st.Page(
        lambda: _render_genai_page(context if context is not None else None, locale),
        title=("GenAI Insights" if is_en else "GenAI Insights"),
        icon=":material/auto_awesome:",
        url_path="genai-insights",
    )
    assistant_page = st.Page(
        lambda: _render_assistant_page(
            context if context is not None else None, locale
        ),
        title=("RAG Assistant" if is_en else "Assistente RAG"),
        icon=":material/forum:",
        url_path="governance-assistant",
    )
    snowflake_page = st.Page(
        lambda: _render_snowflake_page(
            context if context is not None else None, locale
        ),
        title=("Snowflake Explorer" if is_en else "Snowflake Explorer"),
        icon=":material/database:",
        url_path="snowflake-explorer",
    )

    about_page = st.Page(
        lambda: render_about(locale),
        title="About the project" if is_en else "Sobre o projeto",
        icon=":material/info:",
        url_path="about-gap",
    )
    sections: dict[str, list[StreamlitPage]] = {
        ("Executive View" if is_en else "Visão Executiva"): [overview_page],
        "Analytics": [revenue_page, seller_page, cohort_page, eda_page],
        ("Quality & Governance" if is_en else "Qualidade e Governança"): [
            quality_page,
            catalog_page,
            privacy_page,
            publication_page,
            control_center_page,
        ],
        ("Engineering & Integrations" if is_en else "Engenharia e Integrações"): [
            evidence_page,
            n8n_page,
            genai_page,
            assistant_page,
            snowflake_page,
        ],
        ("Project" if is_en else "Projeto"): [about_page],
    }

    navigation = st.navigation(pages=sections, position="sidebar", expanded=True)
    navigation.run()


if __name__ == "__main__":
    main()
