from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from app.components.analytics import cohort_retention, valid_item_grain
from app.i18n import LOCALE_EN_US, Locale
from src.public_mode import is_public_visitor_mode
from src.semantic_layer import build_cohort_slice

COHORT_SLICE_PATH = Path("data/published/semantic/cohort_slice.csv")


def _load_cohort_slice() -> pd.DataFrame:
    if not COHORT_SLICE_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(COHORT_SLICE_PATH)


def _format_decimal(value: int | float, decimal_places: int) -> str:
    if pd.isna(value):
        return "—"
    numeric_value = float(value)
    formatted = f"{numeric_value:,.{decimal_places}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _format_integer(value: int | float) -> str:
    return f"{int(float(value)):,}".replace(",", ".")


def _format_percentage(value: int | float) -> str:
    formatted = _format_decimal(value, 1)
    return formatted if formatted == "—" else f"{formatted}%"


def _format_currency(value: int | float) -> str:
    formatted = _format_decimal(value, 2)
    return formatted if formatted == "—" else f"R$ {formatted}"


def _format_month_offset(value: int | float) -> str:
    return f"Mês {int(float(value))}"


def render_cohort_retention(locale: Locale, df: pd.DataFrame | None = None) -> None:
    is_en = locale == LOCALE_EN_US
    st.title("Customer Retention" if is_en else "Retenção de Clientes")
    st.subheader(
        "Track how many customers return in the months after their first purchase."
        if is_en
        else "Análise por cohorts para acompanhar a permanência de clientes ao longo "
        "dos meses após a primeira compra."
    )
    st.caption(
        "Each cohort compares the number of customers in a given month with its Month 0 population."
        if is_en
        else "A retenção compara, em cada cohort, a quantidade de clientes de cada mês "
        "relativo com o volume do mês inicial."
    )
    st.markdown("### How to read this page" if is_en else "### Como interpretar esta página")
    st.write(
        "Each row groups customers by first purchase month. Columns count the months "
        "since that purchase. Month 0 is the denominator for the cohort."
        if is_en
        else "Cada linha representa um grupo mensal de clientes e cada coluna representa "
        "o número de meses desde a primeira compra. O Mês 0 é o baseline de cada "
        "grupo e serve como denominador para o cálculo de retenção."
    )
    st.caption(
        "Blank cells indicate a missing combination, a partial month, or an unavailable baseline."
        if is_en
        else "Células vazias indicam combinação ausente, mês parcial ou população inicial indisponível."
    )
    st.markdown(
        "**Retention = customers in the month ÷ Month 0 customers × 100**"
        if is_en
        else "**Retenção = clientes no mês relativo ÷ clientes do Mês 0 × 100**"
    )

    if is_public_visitor_mode():
        if df is not None and not df.empty and not valid_item_grain(df):
            st.warning(
                "Retention is unavailable because order-item keys are invalid."
                if is_en
                else "Retenção indisponível: o grão pedido × item não é válido."
            )
            return
        cohort_df = (
            build_cohort_slice(df)
            if df is not None and not df.empty
            else pd.DataFrame()
        )
    else:
        cohort_df = _load_cohort_slice()

    required = {
        "purchase_cohort_month",
        "cohort_order_month_number",
        "customers",
        "avg_ticket",
    }
    if cohort_df.empty or not required.issubset(cohort_df.columns):
        st.info(
            "Dados de retenção não disponíveis neste ambiente."
            if not is_en
            else "Retention data is unavailable in this environment."
        )
        st.caption(
            "A visualização depende do slice semântico de cohorts persistido por "
            "uma execução controlada."
            if not is_en
            else "This view depends on the persisted semantic cohort slice."
        )
        return

    retention = cohort_retention(cohort_df)
    cohort_df = retention
    if cohort_df.empty:
        st.info("Cohort cells are unavailable." if is_en else "Células de coorte indisponíveis.")
        return
    ticket_column = (
        "avg_order_ticket" if "avg_order_ticket" in cohort_df else "avg_ticket"
    )
    ticket_label = (
        "Ticket por pedido"
        if ticket_column == "avg_order_ticket"
        else "Valor médio por item"
    )

    valid_baseline = retention["retention_rate"].notna()
    cohort_count = int(retention.loc[valid_baseline, "purchase_cohort_month"].nunique())
    period_start = str(cohort_df["purchase_cohort_month"].min())
    period_end = str(cohort_df["purchase_cohort_month"].max())
    relative_month_count = int(cohort_df["cohort_order_month_number"].nunique())
    calculable_cells = int(retention["retention_rate"].notna().sum())

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    metric_1.metric("Cohorts analyzed" if is_en else "Cohorts analisados", _format_integer(cohort_count))
    metric_2.metric(
        "Observed period" if is_en else "Período analisado",
        f"{period_start} to {period_end}" if is_en else f"{period_start} a {period_end}",
    )
    metric_3.metric(
        "Relative months covered" if is_en else "Meses relativos representados",
        _format_integer(relative_month_count),
    )
    metric_4.metric(
        "Cells with observable retention" if is_en else "Células com retenção calculável",
        _format_integer(calculable_cells),
    )

    st.markdown("### Leitura executiva")
    st.markdown(
        f"- A análise reúne **{_format_integer(cohort_count)} cohorts mensais**.\n"
        f"- O período observado vai de **{period_start} a {period_end}**.\n"
        f"- Há **{_format_integer(relative_month_count)} meses relativos** "
        "representados.\n"
        f"- Foram calculadas **{_format_integer(calculable_cells)} células de "
        "retenção**."
    )

    retention_pivot = retention.pivot(
        index="purchase_cohort_month",
        columns="cohort_order_month_number",
        values="retention_rate",
    )
    retention_text = retention_pivot.map(_format_percentage)
    retention_offsets = list(retention_pivot.columns)
    retention_offset_labels = [
        _format_month_offset(float(value)) for value in retention_offsets
    ]
    fig_retention = px.imshow(
        retention_pivot,
        text_auto=False,
        aspect="auto",
        color_continuous_scale="Teal",
        range_color=(0, 100),
        title="Matriz de retenção por cohort (%)",
        labels={
            "x": "Meses desde a primeira compra",
            "y": "Cohort de compra",
            "color": "Retenção (%)",
        },
    )
    fig_retention.update_traces(
        text=retention_text.to_numpy(),
        customdata=[retention_offset_labels for _ in retention_pivot.index],
        texttemplate="%{text}",
        hovertemplate=(
            "Cohort: %{y}<br>%{customdata}<br>Retenção: %{text}<extra></extra>"
        ),
    )
    retention_tick_step = max(1, (len(retention_offsets) + 4) // 5)
    fig_retention.update_xaxes(
        tickmode="array",
        tickvals=retention_offsets[::retention_tick_step],
        ticktext=retention_offset_labels[::retention_tick_step],
        title_text="Meses desde a primeira compra",
    )
    fig_retention.update_yaxes(title_text="Cohort de compra")

    ticket_pivot = cohort_df.pivot(
        index="purchase_cohort_month",
        columns="cohort_order_month_number",
        values=ticket_column,
    )
    ticket_text = ticket_pivot.map(_format_currency)
    ticket_offsets = list(ticket_pivot.columns)
    ticket_offset_labels = [
        _format_month_offset(float(value)) for value in ticket_offsets
    ]
    fig_ticket = px.imshow(
        ticket_pivot,
        text_auto=False,
        aspect="auto",
        color_continuous_scale="Blues",
        title=f"{ticket_label} por cohort",
        labels={
            "x": "Meses desde a primeira compra",
            "y": "Cohort de compra",
            "color": f"{ticket_label} (R$)",
        },
    )
    fig_ticket.update_traces(
        text=ticket_text.to_numpy(),
        customdata=[ticket_offset_labels for _ in ticket_pivot.index],
        texttemplate="%{text}",
        hovertemplate=(
            "Cohort: %{y}<br>%{customdata}<br>Ticket médio: %{text}<extra></extra>"
        ),
    )
    ticket_tick_step = max(1, (len(ticket_offsets) + 4) // 5)
    fig_ticket.update_xaxes(
        tickmode="array",
        tickvals=ticket_offsets[::ticket_tick_step],
        ticktext=ticket_offset_labels[::ticket_tick_step],
        title_text="Meses desde a primeira compra",
    )
    fig_ticket.update_yaxes(title_text="Cohort de compra")

    retention_tab, ticket_tab = st.tabs(
        ["Retention", "Average value"] if is_en else ["Retenção", "Ticket médio"]
    )
    with retention_tab:
        st.plotly_chart(fig_retention, width="stretch")
    with ticket_tab:
        st.caption(f"{ticket_label} · valores em reais.")
        st.plotly_chart(fig_ticket, width="stretch")

    if is_public_visitor_mode() and retention["retention_rate"].notna().any():
        st.subheader("Evolução da retenção por coorte")
        observable_cohorts = sorted(
            retention.loc[
                retention["retention_rate"].notna(), "purchase_cohort_month"
            ].unique()
        )
        cohort_month = st.selectbox("Acquisition month" if is_en else "Mês de aquisição", observable_cohorts)
        selected = retention.loc[retention["purchase_cohort_month"].eq(cohort_month)]
        max_offset = int(selected["cohort_order_month_number"].max())
        trend = selected.set_index("cohort_order_month_number").reindex(
            range(max_offset + 1)
        )
        fig_trend = px.line(
            trend,
            y="retention_rate",
            markers=True,
            range_y=(0, 100),
            labels={
                "cohort_order_month_number": "Mês desde a primeira compra",
                "retention_rate": "Retenção (%)",
            },
        )
        fig_trend.update_traces(connectgaps=False)
        st.plotly_chart(fig_trend, width="stretch")
        st.caption(
            "Cada ponto usa a população de Mês 0. Células sem taxa observável aparecem como lacunas."
        )

    technical_table = retention[
        [
            "purchase_cohort_month",
            "cohort_order_month_number",
            "customers",
            "baseline_customers",
            "retention_rate",
            ticket_column,
        ]
    ].sort_values(["purchase_cohort_month", "cohort_order_month_number"])

    executive_table = technical_table[
        [
            "purchase_cohort_month",
            "cohort_order_month_number",
            "customers",
            "retention_rate",
            ticket_column,
        ]
    ].copy()
    executive_table["cohort_order_month_number"] = executive_table[
        "cohort_order_month_number"
    ].map(_format_month_offset)
    executive_table["customers"] = executive_table["customers"].map(_format_integer)
    executive_table["retention_rate"] = executive_table["retention_rate"].map(
        _format_percentage
    )
    executive_table[ticket_column] = executive_table[ticket_column].map(
        _format_currency
    )
    executive_table = executive_table.rename(
        columns={
            "purchase_cohort_month": "Cohort",
            "cohort_order_month_number": "Mês relativo",
            "customers": "Clientes",
            "retention_rate": "Retenção",
            ticket_column: ticket_label,
        }
    )

    st.markdown("### Detalhamento por cohort")
    st.dataframe(
        executive_table,
        width="stretch",
        hide_index=True,
    )

    with st.expander("Detalhes técnicos da retenção", expanded=False):
        st.caption(
            "Os valores técnicos abaixo preservam os identificadores e cálculos "
            "usados na lógica analítica."
        )
        st.dataframe(technical_table, width="stretch", hide_index=True)
