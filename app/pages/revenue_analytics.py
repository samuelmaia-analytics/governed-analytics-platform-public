from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from app.components.analytics import cohort_retention, valid_item_grain
from app.i18n import LOCALE_EN_US, Locale
from src.public_mode import is_public_visitor_mode
from src.semantic_layer import build_category_slice, build_cohort_slice

CATEGORY_SLICE_PATH = Path("data/published/semantic/category_slice.csv")
COHORT_SLICE_PATH = Path("data/published/semantic/cohort_slice.csv")


def _load_semantic_slice(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _format_brl(value: float) -> str:
    formatted = f"{value:,.2f}"
    return f"R$ {formatted.replace(',', '_').replace('.', ',').replace('_', '.')}"


def _shorten_seller_label(value: object) -> str:
    seller_id = str(value)
    return seller_id if len(seller_id) <= 12 else f"…{seller_id[-8:]}"


def _render_executive_kpis(df: pd.DataFrame) -> None:
    amounts = pd.to_numeric(
        df.get("total_item_value", pd.Series(dtype=float)), errors="coerce"
    )
    total = amounts.sum(min_count=1)
    revenue = float(total) if pd.notna(total) else None
    order_count = (
        int(df["order_id"].nunique(dropna=True)) if "order_id" in df.columns else None
    )
    average_ticket = (
        revenue / order_count
        if revenue is not None and order_count is not None and order_count > 0
        else None
    )
    active_sellers = (
        int(df["seller_key"].nunique(dropna=True))
        if "seller_key" in df.columns
        else None
    )

    order_label = (
        f"{order_count:,}".replace(",", ".")
        if order_count is not None
        else "Não disponível"
    )
    seller_label = (
        f"{active_sellers:,}".replace(",", ".")
        if active_sellers is not None
        else "Não disponível"
    )
    revenue_col, orders_col, ticket_col, sellers_col = st.columns([1.5, 1, 1, 1])
    revenue_col.metric(
        "GMV (itens + frete)",
        _format_brl(revenue) if revenue is not None else "Não disponível",
    )
    orders_col.metric("Pedidos", order_label)
    ticket_col.metric(
        "Ticket por pedido",
        _format_brl(average_ticket) if average_ticket is not None else "Não disponível",
    )
    sellers_col.metric(
        "Sellers ativos",
        seller_label,
    )

    st.markdown("### Leitura executiva")
    if (
        revenue is not None
        and order_count is not None
        and average_ticket is not None
        and active_sellers is not None
    ):
        st.markdown(
            f"- A base analisada reúne **{_format_brl(revenue)}** em receita, "
            f"distribuída entre **{order_label} pedidos** e "
            f"**{seller_label} sellers ativos**.\n"
            f"- O ticket médio observado no período é de "
            f"**{_format_brl(average_ticket)}**.\n"
            "- As análises abaixo detalham evolução temporal, concentração por "
            "categoria, cohorts e contribuição dos sellers."
        )
    else:
        st.markdown(
            "- As análises abaixo detalham evolução temporal da receita, "
            "concentração por categoria, comportamento por cohort e desempenho "
            "dos sellers."
        )


def _render_monthly_revenue(df: pd.DataFrame, locale: Locale) -> None:
    is_en = locale == LOCALE_EN_US
    if "total_item_value" not in df.columns:
        st.info(
            "Colunas necessárias não encontradas para série temporal."
            if not is_en
            else "Required columns for time series were not found."
        )
        return

    working_df = df.copy()
    if "order_purchase_timestamp" in working_df:
        dates = pd.to_datetime(working_df["order_purchase_timestamp"], errors="coerce")
        working_df["order_year_month"] = dates.dt.to_period("M").dt.strftime("%Y-%m")
        first, last = dates.min(), dates.max()
        if pd.notna(first) and pd.notna(last):
            st.caption(f"Datas observadas: {first:%d/%m/%Y} a {last:%d/%m/%Y}.")
            if not first.is_month_start or not last.is_month_end:
                st.caption(
                    "A série inclui mês de borda parcial; compare períodos equivalentes."
                )
    if "order_year_month" not in working_df.columns:
        if {"order_year", "order_month"}.issubset(working_df.columns):
            year = pd.to_numeric(working_df["order_year"], errors="coerce")
            month = pd.to_numeric(working_df["order_month"], errors="coerce")
            working_df["order_year_month"] = pd.to_datetime(
                {"year": year, "month": month, "day": 1}, errors="coerce"
            ).dt.strftime("%Y-%m")
        else:
            st.info(
                "Colunas temporais necessárias não encontradas para série mensal."
                if not is_en
                else "Temporal columns required for monthly trend were not found."
            )
            return

    valid_months = (
        working_df["order_year_month"]
        .astype("string")
        .str.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", na=False)
    )
    missing_months = int((~valid_months).sum())
    if missing_months:
        st.caption(
            f"{missing_months:,} itens sem mês válido foram omitidos da série mensal."
        )
    if not valid_months.any():
        st.info("Série mensal indisponível.")
        return

    monthly = (
        working_df.loc[valid_months]
        .groupby("order_year_month")["total_item_value"]
        .sum(min_count=1)
        .reset_index()
    )
    monthly = monthly.rename(columns={"total_item_value": "revenue"})
    monthly = monthly.sort_values("order_year_month")
    st.subheader("Evolução mensal da receita")
    st.caption(
        "Permite visualizar crescimento, sazonalidade e mudanças de nível de "
        "receita ao longo do período."
    )
    fig = px.bar(
        monthly,
        x="order_year_month",
        y="revenue",
        labels={
            "order_year_month": "Ano-mês",
            "revenue": "Receita (R$)",
        },
    )
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig, width="stretch")


def _render_category_pareto(category_slice: pd.DataFrame, locale: Locale) -> None:
    is_en = locale == LOCALE_EN_US
    if category_slice.empty or not {
        "product_category_name_english",
        "revenue",
    }.issubset(category_slice.columns):
        st.info(
            "Slice de categoria indisponível."
            if not is_en
            else "Category slice unavailable."
        )
        return

    category = (
        category_slice.groupby("product_category_name_english", dropna=False)["revenue"]
        .sum()
        .reset_index()
        .sort_values("revenue", ascending=False)
    )
    category["category"] = category["product_category_name_english"].fillna("unknown")
    total_revenue = float(category["revenue"].sum())
    if total_revenue > 0:
        category["cum_pct"] = (category["revenue"].cumsum() / total_revenue) * 100
    else:
        category["cum_pct"] = 0.0

    pareto_cutoff = int((category["cum_pct"] <= 80).sum())
    pareto_cutoff = max(1, pareto_cutoff)

    st.subheader("Concentração de receita por categoria")
    fig = px.bar(
        category.head(15),
        x="category",
        y="revenue",
        labels={"category": "Categoria", "revenue": "Receita (R$)"},
    )
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), xaxis_tickangle=-35)
    st.plotly_chart(fig, width="stretch")
    concentration = f"{category['cum_pct'].iloc[pareto_cutoff - 1]:.1f}".replace(
        ".", ","
    )
    st.caption(
        f"As {pareto_cutoff} categorias de maior receita concentram {concentration}% do total."
    )
    display_category = category[["category", "revenue", "cum_pct"]].rename(
        columns={
            "category": "Categoria",
            "revenue": "Receita",
            "cum_pct": "Cumulativo %",
        }
    )
    display_category["Receita"] = display_category["Receita"].map(_format_brl)
    st.dataframe(
        display_category,
        width="stretch",
        hide_index=True,
    )


def _render_cohort_ticket_and_retention(
    cohort_slice: pd.DataFrame, locale: Locale
) -> None:
    is_en = locale == LOCALE_EN_US
    required = {
        "purchase_cohort_month",
        "cohort_order_month_number",
        "customers",
        "avg_ticket",
    }
    if cohort_slice.empty or not required.issubset(cohort_slice.columns):
        st.info(
            "Slice de cohort indisponível."
            if not is_en
            else "Cohort slice unavailable."
        )
        return

    cohort_df = cohort_retention(cohort_slice)
    ticket_column = (
        "avg_order_ticket" if "avg_order_ticket" in cohort_df else "avg_ticket"
    )
    ticket_label = (
        "Ticket por pedido"
        if ticket_column == "avg_order_ticket"
        else "Valor médio por item"
    )
    if cohort_df.empty:
        st.info("Células de coorte indisponíveis.")
        return

    st.caption(
        "A análise de cohort mostra como ticket médio e retenção evoluem ao "
        "longo dos meses após a primeira compra."
    )

    ticket_pivot = cohort_df.pivot(
        index="purchase_cohort_month",
        columns="cohort_order_month_number",
        values=ticket_column,
    )
    fig_ticket = px.imshow(
        ticket_pivot,
        text_auto=".1f",
        aspect="auto",
        color_continuous_scale="Blues",
        title=f"{ticket_label} por cohort",
        labels={
            "x": "Meses desde a primeira compra",
            "y": "Cohort de aquisição",
            "color": f"{ticket_label} (R$)",
        },
    )
    st.plotly_chart(fig_ticket, width="stretch")

    retention_pivot = cohort_df.pivot(
        index="purchase_cohort_month",
        columns="cohort_order_month_number",
        values="retention_rate",
    )
    fig_retention = px.imshow(
        retention_pivot,
        text_auto=".1f",
        aspect="auto",
        color_continuous_scale="Teal",
        title="Retenção por cohort (%)",
        range_color=(0, 100),
        labels={
            "x": "Meses desde a primeira compra",
            "y": "Cohort de aquisição",
            "color": "Retenção (%)",
        },
    )
    st.plotly_chart(fig_retention, width="stretch")


def _render_top_sellers(df: pd.DataFrame, locale: Locale) -> None:
    is_en = locale == LOCALE_EN_US
    if not {"seller_key", "total_item_value"}.issubset(df.columns):
        st.info(
            "Colunas de seller não encontradas."
            if not is_en
            else "Seller columns not found."
        )
        return
    sellers = (
        df.groupby("seller_key")["total_item_value"]
        .sum()
        .reset_index()
        .sort_values("total_item_value", ascending=False)
        .head(15)
    )
    st.subheader("Top sellers por receita")
    st.caption(
        "Ranking dos sellers com maior contribuição para a receita no período "
        "analisado."
    )
    seller_display = sellers.assign(
        seller_label=sellers["seller_key"].map(_shorten_seller_label)
    )
    fig = px.bar(
        seller_display,
        x="seller_label",
        y="total_item_value",
        title="Top sellers por receita",
        hover_data={"seller_key": True, "seller_label": False},
        labels={
            "seller_label": "Seller",
            "total_item_value": "Receita",
        },
    )
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), xaxis_tickangle=-35)
    st.plotly_chart(fig, width="stretch")


def render_revenue_analytics(df: pd.DataFrame, locale: Locale) -> None:
    is_en = locale == LOCALE_EN_US
    st.title("Revenue and performance" if is_en else "Receita e performance")
    st.write(
        "Track monthly revenue and see where sales concentrate by category and seller."
        if is_en
        else "Acompanhe a receita mensal e veja onde as vendas se concentram por categoria e seller."
    )
    public_mode = is_public_visitor_mode()
    if public_mode:
        st.caption(
            "Synthetic data · Values in BRL"
            if is_en
            else "Dados sintéticos · Valores em reais (BRL)"
        )
    if public_mode and not valid_item_grain(df):
        st.warning("Análise indisponível: o grão pedido × item não é válido.")
        return
    if df.empty and public_mode:
        st.info(
            "Revenue data is unavailable."
            if is_en
            else "Dados de receita indisponíveis."
        )
        return
    st.caption(
        "GMV = valor dos itens + frete, nos estados presentes na fonte. "
        "Ticket por pedido = GMV ÷ pedidos distintos."
    )
    _render_executive_kpis(df)

    category_slice = (
        build_category_slice(df)
        if public_mode
        else _load_semantic_slice(CATEGORY_SLICE_PATH)
    )
    cohort_slice = (
        build_cohort_slice(df)
        if public_mode
        else _load_semantic_slice(COHORT_SLICE_PATH)
    )

    tab_evolution, tab_pareto, tab_cohort, tab_sellers = st.tabs(
        [
            "Evolução da receita",
            "Pareto por categoria",
            "Cohort",
            "Top Sellers",
        ]
    )
    with tab_evolution:
        _render_monthly_revenue(df, locale)
    with tab_pareto:
        _render_category_pareto(category_slice, locale)
    with tab_cohort:
        _render_cohort_ticket_and_retention(cohort_slice, locale)
    with tab_sellers:
        _render_top_sellers(df, locale)

    if public_mode and (category_slice.empty or cohort_slice.empty):
        st.caption(
            "Category or cohort analysis is unavailable for this sample."
            if is_en
            else "A análise por categoria ou coorte está indisponível para esta amostra."
        )
    elif category_slice.empty or cohort_slice.empty:
        st.caption(
            "Execute `python -m src.semantic_layer` para materializar os slices semânticos."
            if not is_en
            else "Run `python -m src.semantic_layer` to materialize semantic slices."
        )
