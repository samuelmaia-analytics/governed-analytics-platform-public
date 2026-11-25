from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.navigation.page import StreamlitPage

from app.components.cards import render_metric_cards
from app.components.ui import PUBLIC_REPOSITORY, render_footer
from app.i18n import LOCALE_EN_US, Locale
from app.pages.publication_governance import (
    PublicationGovernanceSnapshot,
    load_publication_governance_snapshot,
)
from src.cloud_reference import summarize_cost_controls
from src.config import PUBLISHED_MONITORING_DIR
from src.data_lake_layers import summarize_layer_status
from src.governance_types import DataQualityResult, PrivacyRiskResult
from src.public_mode import is_public_visitor_mode
from src.publication_gate import OperationalPublicationGateDecision

GOVERNANCE_HISTORY_PATH = PUBLISHED_MONITORING_DIR / "governance_history.csv"
DEFAULT_PUBLISHED_DATASET = Path("data/published/dashboard/fact_orders_dashboard.csv")


def _load_previous_snapshot() -> dict[str, float] | None:
    if is_public_visitor_mode():
        return None

    if not GOVERNANCE_HISTORY_PATH.exists():
        return None
    try:
        history = pd.read_csv(GOVERNANCE_HISTORY_PATH)
        if len(history) < 2:
            return None
        last = history.iloc[-2]
        return {
            "privacy_risk_score": float(last.get("privacy_risk_score", 0)),
            "data_quality_score": float(last.get("data_quality_score", 0)),
            "failed_rules_count": float(last.get("failed_rules_count", 0)),
        }
    except Exception:
        return None


def _data_freshness(path: Path = DEFAULT_PUBLISHED_DATASET) -> str | None:
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    age_hours = (datetime.now(timezone.utc).timestamp() - mtime) / 3600
    if age_hours < 1:
        return "< 1h"
    if age_hours < 24:
        return f"{int(age_hours)}h"
    days = int(age_hours / 24)
    return f"{days}d"


def _count_critical_failures(quality_results: DataQualityResult) -> int:
    checks = quality_results.get("checks")
    if not isinstance(checks, list):
        return 0
    return sum(
        1
        for check in checks
        if str(check.get("status", "")).strip().upper() == "FAIL"
        and str(check.get("severity", "")).strip().lower() == "critical"
    )


def _render_operational_readiness_section(locale: Locale) -> None:
    is_en = locale == LOCALE_EN_US
    st.subheader(
        "Production-Style Readiness" if is_en else "Prontid\u00e3o operacional simulada"
    )

    layer_status = summarize_layer_status()
    ready_layers = sum(1 for layer in layer_status if layer["ready"])
    cost_summary = summarize_cost_controls()
    guardrail_count = cost_summary["guardrail_count"]
    guardrails = cost_summary["guardrails"]
    if not isinstance(guardrail_count, int):
        raise TypeError("guardrail_count must be an integer")
    if not isinstance(guardrails, list):
        raise TypeError("guardrails must be a list")

    st.caption(
        "AWS is documented as a reference architecture; no cloud resources or credentials are bundled."
        if is_en
        else "AWS est\u00e1 documentada como arquitetura de refer\u00eancia; nenhum recurso cloud ou credencial \u00e9 inclu\u00eddo."
    )

    with st.expander(
        "Infrastructure, layers, and cost controls"
        if is_en
        else "Infraestrutura, camadas e controles de custo"
    ):
        readiness_col1, readiness_col2, readiness_col3 = st.columns(3)
        with readiness_col1:
            st.metric(
                "Data Lake Layers" if is_en else "Camadas do Data Lake",
                f"{ready_layers} / {len(layer_status)}",
            )
        with readiness_col2:
            st.metric(
                "Cost Guardrails" if is_en else "Guardrails de custo",
                guardrail_count,
            )
        with readiness_col3:
            st.metric(
                "Cloud Status" if is_en else "Status cloud",
                "Reference only"
                if not cost_summary["is_provisioned"]
                else "Provisioned",
            )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "layer": layer["layer"],
                        "ready": layer["ready"],
                        "paths": layer["path_count"],
                        "owner_role": layer["owner_role"],
                        "sensitivity": layer["sensitivity_default"],
                    }
                    for layer in layer_status
                ]
            ),
            width="stretch",
        )
        st.markdown(
            "\n".join(
                f"- {guardrail['name']}: {guardrail['control']}"
                for guardrail in guardrails
            )
        )


def render_executive_hero(locale: Locale, *, public_mode: bool) -> None:
    is_en = locale == LOCALE_EN_US
    label = "Independent portfolio" if is_en else "Portfólio independente"
    if public_mode:
        label += " · Synthetic data" if is_en else " · Dados sintéticos"
    lead = (
        "Marketplace performance with auditable data."
        if is_en
        else "Desempenho de marketplace com dados auditáveis."
    )
    description = (
        "Explore revenue, seller performance and customer retention. "
        "Use the governance views to verify the checks behind the numbers."
        if is_en
        else "Explore receita, desempenho de sellers e retenção de clientes. "
        "Confira na governança as validações que sustentam os indicadores."
    )
    st.markdown(
        f"""
<div class="gap-hero">
  <p class="gap-kicker">{label}</p>
  <h1>Governed Analytics Platform</h1>
  <p class="gap-lead">{lead}</p>
  <p>{description}</p>
</div>
""",
        unsafe_allow_html=True,
    )


def render_governed_flow(locale: Locale) -> None:
    is_en = locale == LOCALE_EN_US
    st.header(
        "How data reaches a decision" if is_en else "Como os dados chegam à decisão"
    )
    st.write(
        "Inconsistent data and unintended exposure undermine confidence in analytics."
        if is_en
        else "Dados inconsistentes e exposição indevida comprometem a confiança nas análises."
    )
    stages = (
        (
            (
                "Ingest and transform",
                "Bronze receives the input. Silver standardizes it.",
            ),
            (
                "Validate and isolate",
                "Contracts and rules check records. Quarantine isolates rejections.",
            ),
            (
                "Publish and consume",
                "Gold feeds the semantic layer. The Publication Gate controls release.",
            ),
        )
        if is_en
        else (
            (
                "Ingerir e transformar",
                "A Bronze recebe a origem. A Silver padroniza os dados.",
            ),
            (
                "Validar e isolar",
                "Contratos e regras validam registros. A Quarantine isola rejeições.",
            ),
            (
                "Publicar e consumir",
                "A Gold alimenta a camada semântica. O Publication Gate controla a liberação.",
            ),
        )
    )
    for column, (title, description) in zip(st.columns(3), stages, strict=True):
        with column:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.write(description)


def render_executive_overview(
    df: pd.DataFrame,
    classification_df: pd.DataFrame,
    risk_result: PrivacyRiskResult,
    quality_results: DataQualityResult,
    locale: Locale,
    *,
    business_page: StreamlitPage | None = None,
    governance_page: StreamlitPage | None = None,
    governance_snapshot: PublicationGovernanceSnapshot | None = None,
    duckdb_version: str | None = None,
    uses_persisted_governance: bool = False,
    quick_pages: dict[str, StreamlitPage] | None = None,
    public_gate: OperationalPublicationGateDecision | None = None,
) -> None:
    is_en = locale == LOCALE_EN_US
    public_mode = is_public_visitor_mode()

    snapshot = governance_snapshot or (
        load_publication_governance_snapshot() if uses_persisted_governance else None
    )
    unavailable = "Unavailable" if is_en else "Indispon\u00edvel"
    missing_evidence = "No evidence" if is_en else "Sem evid\u00eancia"

    render_executive_hero(locale, public_mode=public_mode)

    prev = _load_previous_snapshot()

    quality_score = max(0, 100 - quality_results["failed_checks_count"] * 10)
    freshness = None if public_mode else _data_freshness()
    critical_failures = _count_critical_failures(quality_results)

    risk_delta: int | None = None
    quality_delta: int | None = None
    failures_delta: int | None = None
    if prev is not None:
        risk_delta = int(risk_result["score"]) - int(prev["privacy_risk_score"])
        quality_delta = quality_score - int(prev["data_quality_score"])
        failures_delta = quality_results["failed_checks_count"] - int(
            prev["failed_rules_count"]
        )

    publication_status = (
        unavailable if snapshot is None else snapshot.historical_decision
    )
    contracts_status = unavailable
    if snapshot is not None:
        contracts_status = (
            snapshot.schema.display if snapshot.schema.total > 0 else missing_evidence
        )

    st.header("Session overview" if is_en else "Resumo da sessão")
    checks = quality_results.get("checks", [])
    render_metric_cards(
        [
            {
                "label": "Analyzed records" if is_en else "Registros analisados",
                "value": f"{len(df):,}" if is_en else f"{len(df):,}".replace(",", "."),
            },
            {
                "label": "Data Quality Score",
                "value": f"{quality_score} / 100",
                "delta": f"{quality_delta:+d}" if quality_delta is not None else None,
            },
            {
                "label": "Privacy Risk Score",
                "value": f"{risk_result['score']} / 100",
                "delta": f"{risk_delta:+d}" if risk_delta is not None else None,
            },
            {
                "label": "Quality checks" if is_en else "Validações de qualidade",
                "value": str(len(checks)) if checks else "—",
            },
            {
                "label": "Critical failures" if is_en else "Falhas críticas",
                "value": str(critical_failures) if checks else "—",
            },
        ],
        max_columns=3,
    )
    st.caption(
        "Session diagnostics for the loaded input. The quality score deducts 10 points per failed check."
        if is_en
        else "Diagnósticos do dataset carregado. O score de qualidade desconta 10 pontos por validação reprovada."
    )

    if public_mode and public_gate is not None:
        st.header("Publication controls" if is_en else "Controle de publicação")
        statuses = (
            {
                "APPROVED": "Approved",
                "APPROVED_WITH_WARNINGS": "Approved with warnings",
                "BLOCKED": "Blocked",
            }
            if is_en
            else {
                "APPROVED": "Aprovado",
                "APPROVED_WITH_WARNINGS": "Aprovado com alertas",
                "BLOCKED": "Bloqueado",
            }
        )
        render_metric_cards(
            [
                {
                    "label": "Operational gate" if is_en else "Gate operacional",
                    "value": statuses[public_gate.decision],
                }
            ],
            max_columns=1,
        )
        st.caption(
            "Current check of quality and authorization for the synthetic sample."
            if is_en
            else "Verificação atual de qualidade e autorização da amostra sintética."
        )

    if public_mode:
        st.caption(
            "Historical pipeline evidence is restricted to the controlled environment."
            if is_en
            else "As evidências históricas do pipeline ficam no ambiente controlado."
        )
    else:
        st.header("Publication evidence" if is_en else "Evidências de publicação")
        render_metric_cards(
            [
                {"label": "Publication Gate", "value": publication_status},
                {
                    "label": "Data contracts" if is_en else "Contratos de dados",
                    "value": contracts_status,
                },
            ],
            max_columns=2,
        )
        if snapshot is None:
            st.info(
                "No recorded decision for this input. The Publication Gate page explains the available evidence."
                if is_en
                else "Sem decisão registrada para este dataset. Consulte as evidências disponíveis no Publication Gate."
            )
        else:
            st.caption(
                "Recorded evidence from the published dataset."
                if is_en
                else "Evidência registrada do dataset publicado."
            )

    render_governed_flow(locale)

    if business_page is not None or governance_page is not None or quick_pages:
        st.header("Explore the platform" if is_en else "Explore a plataforma")
        links: list[tuple[str, StreamlitPage | None, str]] = [
            (
                "Publication Gate" if is_en else "Publication Gate",
                governance_page,
                ":material/policy:",
            ),
            (
                "Business KPIs" if is_en else "Indicadores anal\u00edticos",
                business_page,
                ":material/insights:",
            ),
            (
                "Data Quality" if is_en else "Data Quality",
                (quick_pages or {}).get("data_quality"),
                ":material/check_circle:",
            ),
            (
                "Contracts & Catalog" if is_en else "Contratos e Cat\u00e1logo",
                (quick_pages or {}).get("data_catalog"),
                ":material/table_view:",
            ),
            (
                "LGPD & Privacy" if is_en else "LGPD e Privacidade",
                (quick_pages or {}).get("lgpd_privacy"),
                ":material/policy:",
            ),
            (
                "Control Center" if is_en else "Central de Controles",
                (quick_pages or {}).get("control_center"),
                ":material/admin_panel_settings:",
            ),
        ]
        links = [link for link in links if link[1] is not None]
        for start in range(0, len(links), 3):
            row = links[start : start + 3]
            cols = st.columns(len(row))
            for idx, (label, page, icon) in enumerate(row):
                with cols[idx]:
                    if page is None:
                        continue
                    st.page_link(page, label=label, icon=icon, width="stretch")

    personal_fields = int(
        classification_df["lgpd_classification"]
        .isin(["personal_data", "sensitive_personal_data"])
        .sum()
    )
    suppressed_columns = int(
        classification_df["recommended_action"]
        .isin(["anonymize", "remove", "pseudonymize"])
        .sum()
    )
    sensitive_count = int(
        (classification_df["lgpd_classification"] == "sensitive_personal_data").sum()
    )
    status = (
        (
            "Healthy"
            if quality_results["failed_checks_count"] == 0
            else "Attention Required"
        )
        if is_en
        else (
            "Saud\u00e1vel"
            if quality_results["failed_checks_count"] == 0
            else "Requer aten\u00e7\u00e3o"
        )
    )

    st.divider()
    with st.expander(
        "Detailed governance metrics"
        if is_en
        else "M\u00e9tricas detalhadas de governan\u00e7a",
        expanded=False,
    ):
        st.caption(
            "Diagnostic indicators from the demonstration environment."
            if is_en
            else "Indicadores diagn\u00f3sticos do ambiente demonstrativo."
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Columns" if is_en else "Total de colunas", df.shape[1])
            st.metric(
                "Personal Fields" if is_en else "Campos pessoais", personal_fields
            )
        with col2:
            st.metric(
                "LGPD Risk Score" if is_en else "Score de risco LGPD",
                f"{risk_result['score']} / 100",
                delta=risk_delta,
                delta_color="inverse",
            )
            st.metric(
                "Data Quality Score" if is_en else "Score de qualidade",
                f"{quality_score} / 100",
                delta=quality_delta,
            )
        with col3:
            st.metric(
                "Quality Failures" if is_en else "Falhas de qualidade",
                quality_results["failed_checks_count"],
                delta=failures_delta,
                delta_color="inverse",
            )
            st.metric(
                "Quality diagnostics" if is_en else "Diagnóstico de qualidade", status
            )

        extra_col1, extra_col2, extra_col3 = st.columns(3)
        with extra_col1:
            st.metric(
                "Data Freshness" if is_en else "Freshness dos dados",
                freshness
                if freshness
                else (
                    (
                        "Unavailable in public view"
                        if is_en
                        else "Indisponível no perfil público"
                    )
                    if public_mode
                    else unavailable
                ),
            )
        with extra_col2:
            st.metric(
                "Fields with recommended protection"
                if is_en
                else "Campos com proteção recomendada",
                suppressed_columns,
                help=(
                    "Columns with action: anonymize, remove or pseudonymize."
                    if is_en
                    else "Colunas com a\u00e7\u00e3o: anonimizar, remover ou pseudonimizar."
                ),
            )
        with extra_col3:
            st.metric(
                "Sensitive Data Columns" if is_en else "Dados sens\u00edveis",
                sensitive_count,
            )
        if duckdb_version is not None:
            st.caption(f"DuckDB: {duckdb_version}")

    if not public_mode:
        _render_operational_readiness_section(locale)
    st.markdown(
        f"[{'Technical validation and CI history' if is_en else 'Validação técnica e histórico do CI'}]"
        f"({PUBLIC_REPOSITORY}/actions)"
    )
    render_footer(locale=locale)
