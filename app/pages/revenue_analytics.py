from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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


def _format_brl(value: float, *, is_en: bool = False) -> str:
    formatted = f"{value:,.2f}"
    if is_en:
        return f"R$ {formatted}"
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


@dataclass(frozen=True)
class MonthlyRevenue:
    data: pd.DataFrame
    first_purchase: pd.Timestamp | None
    last_purchase: pd.Timestamp | None
    undated_items: int
    undated_revenue: float


def _build_monthly_revenue(df: pd.DataFrame) -> MonthlyRevenue:
    first = last = None
    if "order_purchase_timestamp" in df:
        dates = pd.to_datetime(df["order_purchase_timestamp"], errors="coerce")
        if dates.notna().any():
            first, last = pd.Timestamp(dates.min()), pd.Timestamp(dates.max())
        months = dates.dt.tz_localize(None).dt.to_period("M")
    elif "order_year_month" in df:
        labels = df["order_year_month"].astype("string")
        valid = labels.str.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", na=False)
        months = pd.to_datetime(
            labels.where(valid), format="%Y-%m", errors="coerce"
        ).dt.to_period("M")
    elif {"order_year", "order_month"}.issubset(df.columns):
        year = pd.to_numeric(df["order_year"], errors="coerce")
        month = pd.to_numeric(df["order_month"], errors="coerce")
        valid = year.mod(1).eq(0) & month.mod(1).eq(0)
        months = pd.to_datetime(
            {"year": year.where(valid), "month": month.where(valid), "day": 1},
            errors="coerce",
        ).dt.to_period("M")
    else:
        months = pd.Series(pd.NaT, index=df.index, dtype="period[M]")

    amounts = pd.to_numeric(df["total_item_value"], errors="coerce").replace(
        [float("inf"), float("-inf")], float("nan")
    )
    undated = months.isna()
    undated_items = int(undated.sum())
    undated_revenue = float(amounts[undated].sum())
    revenue = amounts.groupby(months).sum(min_count=1)
    if revenue.empty:
        return MonthlyRevenue(
            pd.DataFrame(), first, last, undated_items, undated_revenue
        )

    calendar = pd.period_range(revenue.index.min(), revenue.index.max(), freq="M")
    monthly = revenue.reindex(calendar).rename("revenue").to_frame()
    monthly["partial"] = False
    monthly["unverified_boundary"] = False
    if first is not None and last is not None:
        monthly.loc[calendar[0], "partial"] = not first.is_month_start
        monthly.loc[calendar[-1], "partial"] |= not last.is_month_end
    else:
        monthly["unverified_boundary"] = monthly.index.isin([calendar[0], calendar[-1]])
    complete = monthly["revenue"].mask(
        monthly["partial"] | monthly["unverified_boundary"]
    )
    previous = complete.shift()
    monthly["mom"] = (
        (complete.div(previous.where(previous.ne(0))) - 1)
        .mul(100)
        .replace([float("inf"), float("-inf")], float("nan"))
    )
    monthly["moving_average"] = complete.rolling(3, min_periods=3).mean()
    return MonthlyRevenue(monthly, first, last, undated_items, undated_revenue)


def _render_monthly_revenue(df: pd.DataFrame, locale: Locale) -> None:
    is_en = locale == LOCALE_EN_US
    if "total_item_value" not in df:
        st.info(
            "Revenue column unavailable."
            if is_en
            else "Coluna de receita indisponível."
        )
        return
    result = _build_monthly_revenue(df)
    monthly = result.data
    if result.undated_items:
        amount = _format_brl(result.undated_revenue, is_en=is_en)
        count = f"{result.undated_items:,}"
        st.caption(
            f"Excluded from the chart due to an invalid or missing purchase month: {count} items ({amount})."
            if is_en
            else f"Itens omitidos do gráfico por mês de compra inválido ou ausente: {count.replace(',', '.')} ({amount})."
        )
    if monthly.empty or monthly["revenue"].isna().all():
        st.info(
            "Monthly revenue unavailable." if is_en else "Série mensal indisponível."
        )
        return

    st.subheader("Monthly GMV" if is_en else "Evolução mensal do GMV")
    if result.first_purchase is not None and result.last_purchase is not None:
        st.caption(
            f"Observed dates: {result.first_purchase:%Y-%m-%d} to {result.last_purchase:%Y-%m-%d}."
            if is_en
            else f"Datas observadas: {result.first_purchase:%d/%m/%Y} a {result.last_purchase:%d/%m/%Y}."
        )
    else:
        st.caption(
            "The source provides month-level dates. Coverage of the first and last month cannot be verified."
            if is_en
            else "A fonte informa apenas o mês. A cobertura do primeiro e do último mês não pode ser verificada."
        )
    st.caption(
        "Hatched bars mark partial months or unverified coverage. MoM compares two consecutive complete months with a nonzero prior value. "
        "The moving average requires three consecutive complete months. Both calculations stop at gaps."
        if is_en
        else "Barras hachuradas indicam meses parciais ou com cobertura não verificada. O MoM compara dois meses completos consecutivos e exige receita anterior diferente de zero. "
        "A média móvel exige três meses completos consecutivos. Lacunas interrompem os dois cálculos."
    )
    if is_public_visitor_mode():
        st.caption(
            "The data are synthetic and represent a demonstration scenario. Observed fluctuations and patterns should not be interpreted as proven seasonality in real sales."
            if is_en
            else "Os dados são sintéticos e representam um cenário demonstrativo. As oscilações e padrões observados não devem ser interpretados como sazonalidade comprovada de vendas reais."
        )

    unavailable = "Unavailable" if is_en else "Indisponível"
    partial = "Partial month" if is_en else "Mês parcial"
    unverified = "Coverage unverified" if is_en else "Cobertura não verificada"
    monthly_label = "Monthly GMV" if is_en else "GMV mensal"
    average_label = "3-month moving average" if is_en else "Média móvel de 3 meses"
    mom_label = "MoM change" if is_en else "Variação MoM"
    customdata = []
    for month, row in monthly.iterrows():
        mom = f"{row['mom']:+.1f}%" if pd.notna(row["mom"]) else unavailable
        customdata.append(
            [
                str(month),
                _format_brl(row["revenue"], is_en=is_en)
                if pd.notna(row["revenue"])
                else unavailable,
                mom if is_en else mom.replace(".", ","),
                _format_brl(row["moving_average"], is_en=is_en)
                if pd.notna(row["moving_average"])
                else unavailable,
                f"<br>{partial}"
                if row["partial"]
                else f"<br>{unverified}"
                if row["unverified_boundary"]
                else "",
            ]
        )
    hover = (
        "<b>%{customdata[0]}</b>%{customdata[4]}<br>"
        f"{monthly_label}: %{{customdata[1]}}<br>{mom_label}: %{{customdata[2]}}<br>"
        f"{average_label}: %{{customdata[3]}}<extra></extra>"
    )
    x = monthly.index.astype(str) + "-01"
    fig = go.Figure(
        go.Bar(
            x=x,
            y=monthly["revenue"],
            name=monthly_label,
            marker=dict(
                color="#467fb1",
                pattern_shape=[
                    "/" if flagged else ""
                    for flagged in monthly["partial"] | monthly["unverified_boundary"]
                ],
            ),
            customdata=customdata,
            hovertemplate=hover,
        )
    )
    fig.add_scatter(
        x=x,
        y=monthly["moving_average"],
        name=average_label,
        mode="lines+markers",
        line=dict(color="#b75b16", width=3),
        marker=dict(size=5),
        connectgaps=False,
        customdata=customdata,
        hovertemplate=hover,
    )
    fig.update_layout(
        margin=dict(l=12, r=12, t=12, b=12),
        height=390,
        legend=dict(orientation="h", yanchor="top", y=-0.14),
        xaxis=dict(type="date", tickformat="%m/%Y", nticks=6, fixedrange=True),
        yaxis=dict(tickprefix="R$ ", separatethousands=True, nticks=5, fixedrange=True),
        separators=".," if is_en else ",.",
    )
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
    if is_public_visitor_mode():
        prefix = "Product group" if is_en else "Grupo de produtos"
        aliases = {
            f"synthetic_category_{i}": f"{prefix} {letter}"
            for i, letter in enumerate("ABCDE")
        }
        category["category"] = category["category"].replace(aliases)
    total_revenue = float(category["revenue"].sum())
    if total_revenue > 0:
        category["cum_pct"] = (category["revenue"].cumsum() / total_revenue) * 100
    else:
        category["cum_pct"] = 0.0

    st.subheader(
        "Revenue concentration" if is_en else "Concentração de receita por categoria"
    )
    if is_public_visitor_mode():
        st.caption(
            "Groups A–E identify categories in the synthetic sample."
            if is_en
            else "Os grupos A–E identificam as categorias da amostra sintética."
        )
    fig = px.bar(
        category.head(15),
        x="revenue",
        y="category",
        orientation="h",
        labels={
            "category": "Category" if is_en else "Categoria",
            "revenue": "GMV (R$)",
        },
    )
    fig.update_layout(
        margin=dict(l=12, r=12, t=12, b=12),
        height=max(240, 32 * min(15, len(category)) + 60),
        yaxis=dict(autorange="reversed", title=None),
        xaxis=dict(tickprefix="R$ "),
    )
    st.plotly_chart(fig, width="stretch")
    # Include the first category that reaches the threshold.
    pareto_cutoff = int(category["cum_pct"].lt(80).argmin()) + 1
    concentration = f"{category['cum_pct'].iloc[pareto_cutoff - 1]:.2f}".replace(
        ".", ","
    )
    if total_revenue > 0:
        st.caption(
            f"Categories needed to reach 80% of GMV: {pareto_cutoff} ({concentration.replace(',', '.')}%)."
            if is_en
            else f"Categorias necessárias para atingir 80% do GMV: {pareto_cutoff} ({concentration}% acumulado)."
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
        "Track monthly GMV and see where sales concentrate by category and seller."
        if is_en
        else "Acompanhe o GMV mensal e veja onde as vendas se concentram por categoria e seller."
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
        "GMV = item value + freight across all order statuses present in the source. "
        "Average order value = GMV ÷ distinct orders."
        if is_en
        else "GMV = valor dos itens + frete, para todos os status de pedido presentes na fonte. "
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
            "GMV trend" if is_en else "Evolução do GMV",
            "Category Pareto" if is_en else "Pareto por categoria",
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
