from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from app.i18n import LOCALE_EN_US, Locale
from src.governance_types import DataQualityResult

_STATUS_LABELS = {
    "PASS": "APROVADO",
    "WARN": "ALERTA",
    "FAIL": "FALHA",
}

_SEVERITY_LABELS = {
    "high": "ALTA",
    "medium": "MÉDIA",
    "low": "BAIXA",
}

_CHECK_LABELS = {
    "order_id_unique": "Unicidade do pedido",
    "revenue_accepted_range": "Faixa válida de receita",
    "revenue_no_negative": "Receita não negativa",
    "order_status_allowed_values": "Status de pedido permitido",
}

_COLUMN_LABELS = {
    "order_id": "ID do pedido",
    "revenue": "Receita",
    "order_status": "Status do pedido",
    "seller_state": "Estado do seller",
    "product_category": "Categoria do produto",
    "delivery_time_days": "Tempo de entrega (dias)",
    "estimated_days": "Prazo estimado (dias)",
    "customer_unique_id": "Cliente",
}

_CHART_COLUMN_LABELS = {
    "estimated_delay_days": "Desvio do prazo",
    "order_delivered_customer_date": "Data de entrega",
    "carrier_delivery_time_days": "Prazo da transportadora",
    "delivery_time_days": "Tempo de entrega",
    "product_category_name_english": "Categoria (inglês)",
    "product_category_name": "Categoria produto",
    "seller_dispatch_time_days": "Despacho seller",
    "review_score_mean": "Avaliação média",
    "seller_avg_delivery_days": "Entrega média seller",
    "order_id": "ID pedido",
    "order_item_id": "Item pedido",
    "order_month": "Mês pedido",
    "order_status": "Status pedido",
    "customer_unique_id": "Cliente",
    "order_estimated_delivery_date": "Entrega estimada",
    "order_date": "Data pedido",
    "order_year": "Ano pedido",
    "order_purchase_timestamp": "Data da compra",
    "seller_order_count": "Pedidos seller",
    "seller_volume_tier": "Faixa de volume",
}

_RECOMMENDATION_LABELS = {
    "Ensure order identifiers are unique in the analytical grain.": (
        "Garantir unicidade dos identificadores de pedido na granularidade analítica."
    ),
    "Review outlier revenue records and business rule boundaries.": (
        "Revisar valores atípicos de receita e os limites definidos pelas "
        "regras de negócio."
    ),
    "Negative revenue should be justified or corrected.": (
        "Valores negativos de receita devem ser justificados ou corrigidos."
    ),
    "Standardize order status values according to contract.": (
        "Padronizar os valores de status do pedido conforme o contrato de dados."
    ),
}

_EXECUTIVE_COLUMN_LABELS = {
    "check_name": "Validação",
    "status": "Status",
    "severity": "Severidade",
    "affected_columns": "Colunas afetadas",
    "affected_rows": "Linhas afetadas",
    "recommendation": "Recomendação",
    "rule_source": "Origem da regra",
}


def _humanize_identifier(value: object) -> str:
    return str(value).replace("_", " ").strip().capitalize()


def _display_check_name(value: object) -> str:
    technical_name = str(value)
    return _CHECK_LABELS.get(technical_name, _humanize_identifier(technical_name))


def _display_column_name(value: object) -> str:
    technical_name = str(value)
    return _COLUMN_LABELS.get(technical_name, _humanize_identifier(technical_name))


def _display_chart_column_name(value: object) -> str:
    technical_name = str(value)
    return _CHART_COLUMN_LABELS.get(technical_name, _display_column_name(value))


def _display_affected_columns(value: object) -> object:
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_display_column_name(column) for column in value)
    if isinstance(value, str):
        return ", ".join(
            _display_column_name(column.strip()) for column in value.split(",")
        )
    return value


def _build_executive_table(quality_table: pd.DataFrame) -> pd.DataFrame:
    available_columns = [
        column for column in _EXECUTIVE_COLUMN_LABELS if column in quality_table
    ]
    display_table = quality_table.loc[:, available_columns].copy()
    if "check_name" in display_table:
        display_table["check_name"] = display_table["check_name"].map(
            _display_check_name
        )
    if "status" in display_table:
        display_table["status"] = display_table["status"].map(
            lambda value: _STATUS_LABELS.get(str(value).upper(), str(value))
        )
    if "severity" in display_table:
        display_table["severity"] = display_table["severity"].map(
            lambda value: _SEVERITY_LABELS.get(str(value).lower(), str(value))
        )
    if "affected_columns" in display_table:
        display_table["affected_columns"] = display_table["affected_columns"].map(
            _display_affected_columns
        )
    if "recommendation" in display_table:
        display_table["recommendation"] = display_table["recommendation"].map(
            lambda value: _RECOMMENDATION_LABELS.get(str(value), str(value))
        )
    return display_table.rename(columns=_EXECUTIVE_COLUMN_LABELS)


def _format_integer(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def render_data_quality(
    quality_results: DataQualityResult, quality_table: pd.DataFrame, locale: Locale
) -> None:
    is_en = locale == LOCALE_EN_US
    st.title("Data Quality" if is_en else "Qualidade dos Dados")
    st.markdown(
        "Review the integrity, consistency, and business rule checks applied before publication."
        if is_en
        else "Visão executiva dos controles de integridade, consistência e regras "
        "de qualidade aplicados antes da publicação analítica."
    )
    st.caption(
        "The indicators reflect technical checks on the demonstration dataset."
        if is_en
        else "Os indicadores apresentados refletem validações técnicas do dataset "
        "demonstrativo utilizado no projeto de portfólio."
    )
    st.markdown("### How to read this page" if is_en else "### Como interpretar esta página")
    st.write(
        "Use the results to see which checks passed and which need review before analytical use."
        if is_en
        else "A página demonstra como a plataforma identifica falhas de integridade, "
        "inconsistências e violações de regras antes que os dados sejam "
        "disponibilizados para consumo analítico."
    )

    failed_checks_count = int(quality_results["failed_checks_count"])
    quality_score = max(0, 100 - failed_checks_count * 10)

    total_checks = len(quality_table)
    pass_count = (
        int((quality_table["status"] == "PASS").sum())
        if "status" in quality_table.columns
        else 0
    )
    warn_count = (
        int((quality_table["status"] == "WARN").sum())
        if "status" in quality_table.columns
        else 0
    )
    fail_count = (
        int((quality_table["status"] == "FAIL").sum())
        if "status" in quality_table.columns
        else 0
    )

    critical_fail_count = 0
    high_fail_count = 0
    medium_fail_count = 0
    if {"status", "severity"}.issubset(quality_table.columns):
        failed_df = quality_table[quality_table["status"] == "FAIL"]
        critical_fail_count = int((failed_df["severity"] == "critical").sum())
        high_fail_count = int((failed_df["severity"] == "high").sum())
        medium_fail_count = int((failed_df["severity"] == "medium").sum())

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total checks" if is_en else "Total de validações", _format_integer(total_checks))
    with col2:
        st.metric("Passed" if is_en else "Aprovadas", _format_integer(pass_count))
    with col3:
        st.metric("Warnings" if is_en else "Alertas", _format_integer(warn_count))
    with col4:
        st.metric("Failed" if is_en else "Falhas", _format_integer(fail_count))

    col5, col6, col7 = st.columns(3)
    with col5:
        st.metric("Total rows" if is_en else "Total de linhas", _format_integer(quality_results["total_rows"]))
    with col6:
        st.metric("Total columns" if is_en else "Total de colunas", _format_integer(quality_results["total_columns"]))
    with col7:
        st.metric(
            "Quality score" if is_en else "Score de qualidade",
            f"{quality_score} / 100" if total_checks else "—",
        )
    st.caption(
        "When no configured check fails, the score is 100/100. "
        "Some checks allow missing values."
        if is_en
        else "O score de 100/100 indica que nenhuma regra configurada foi reprovada. "
        "Os dados ainda podem conter valores nulos quando as regras os permitem."
    )

    st.markdown("### Leitura executiva")
    st.markdown(
        f"- **{pass_count}** validações foram aprovadas, **{warn_count}** "
        f"geraram alerta e **{fail_count}** apresentaram falha.\n"
        f"- O score de qualidade registrado para o cenário é "
        f"**{quality_score} / 100**."
    )

    null_profile = pd.DataFrame(
        list(quality_results["null_pct_by_column"].items()),
        columns=["column_name", "null_pct"],
    ).sort_values("null_pct", ascending=False)
    incomplete_fields = null_profile.loc[null_profile["null_pct"].gt(0)]
    if not null_profile.empty and incomplete_fields.empty:
        st.markdown("### Percentual de valores nulos por campo")
        st.info("Nenhum valor nulo encontrado nos campos avaliados.")
        st.dataframe(
            null_profile.rename(
                columns={"column_name": "Campo", "null_pct": "Nulos (%)"}
            ),
            column_config={
                "Nulos (%)": st.column_config.NumberColumn(format="%.2f %%")
            },
            width="stretch",
            hide_index=True,
        )
    elif not incomplete_fields.empty:
        display_null_profile = incomplete_fields.head(20).assign(
            column_label=incomplete_fields["column_name"].map(
                _display_chart_column_name
            ),
            formatted_pct=incomplete_fields["null_pct"].map(
                lambda value: f"{value:.2f}".replace(".", ",") + " %"
            ),
        )
        st.markdown("### Percentual de valores nulos por campo")
        st.caption(
            f"Cada percentual usa as {_format_integer(quality_results['total_rows'])} "
            "linhas avaliadas como denominador."
        )
        null_chart = (
            alt.Chart(display_null_profile)
            .mark_bar(cornerRadiusEnd=3, orient="horizontal")
            .encode(
                x=alt.X(
                    "null_pct:Q",
                    title="Percentual de valores nulos (%)",
                    axis=alt.Axis(tickCount=5, labelExpr="replace(datum.label, '.', ',')"),
                ),
                y=alt.Y(
                    "column_label:N",
                    title="Campo",
                    sort=display_null_profile["column_label"].tolist(),
                    axis=alt.Axis(labelLimit=125, labelPadding=6, labelOverlap=False),
                ),
                tooltip=[
                    alt.Tooltip("column_label:N", title="Campo"),
                    alt.Tooltip("column_name:N", title="Nome técnico"),
                    alt.Tooltip("formatted_pct:N", title="Valores nulos"),
                ],
            )
            .properties(height=100 + 28 * len(display_null_profile))
        )
        st.altair_chart(null_chart, width="stretch")

    st.markdown("### Resultado das validações")
    if "status" in quality_table and total_checks:
        display_status = pd.DataFrame(
            {
                "status": list(_STATUS_LABELS),
                "status_label": list(_STATUS_LABELS.values()),
                "count": [pass_count, warn_count, fail_count],
            }
        )
        status_chart = (
            alt.Chart(display_status)
            .mark_bar(cornerRadiusEnd=3, orient="horizontal")
            .encode(
                x=alt.X("count:Q", title="Quantidade", axis=alt.Axis(tickMinStep=1)),
                y=alt.Y(
                    "status_label:N",
                    title="Status",
                    sort=list(_STATUS_LABELS.values()),
                    axis=alt.Axis(labelPadding=6, labelOverlap=False),
                ),
                tooltip=[
                    alt.Tooltip("status_label:N", title="Status"),
                    alt.Tooltip("status:N", title="Código"),
                    alt.Tooltip("count:Q", title="Quantidade", format="d"),
                ],
            )
            .properties(height=180)
        )
        st.altair_chart(status_chart, width="stretch")

    st.markdown("### Falhas por severidade crítica, alta ou média")
    if {"status", "severity"}.issubset(quality_table.columns):
        critical_failed = quality_table[
            (quality_table["status"] == "FAIL")
            & (quality_table["severity"].isin(["critical", "high", "medium"]))
        ]
        if critical_failed.empty:
            st.success("Nenhuma falha de severidade crítica, alta ou média encontrada.")
        else:
            st.dataframe(
                _build_executive_table(critical_failed),
                width="stretch",
                hide_index=True,
            )

    st.markdown("### Resultado diagnóstico de qualidade")
    st.caption(
        "Score = 100 menos 10 pontos por falha, com mínimo zero. Consulte o Publication Gate para a decisão de publicação."
    )
    if total_checks == 0:
        st.info("Sem resultados de validação.")
    elif critical_fail_count or high_fail_count:
        st.error("Falhas críticas ou altas")
    elif fail_count or warn_count:
        st.warning("Requer revisão")
    else:
        st.success("Validações executadas sem falhas ou alertas.")

    with st.expander("Detalhes técnicos das validações", expanded=False):
        st.metric("PASS / WARN / FAIL", f"{pass_count} / {warn_count} / {fail_count}")
        st.metric(
            "Severity raw (high / medium)",
            f"{high_fail_count} / {medium_fail_count}",
        )
        st.dataframe(quality_table, width="stretch", hide_index=True)
