from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from app.components.analytics import filtered_seller_order_count, valid_item_grain
from app.i18n import LOCALE_EN_US, Locale
from src.public_mode import is_public_visitor_mode
from src.semantic_layer import build_seller_slice

SELLER_SLICE_PATH = Path("data/published/semantic/seller_slice.csv")

_TIER_LABELS = {
    "all": "Todos",
    "long_tail": "Cauda longa",
    "scaled": "Em escala",
    "core": "Core",
    "strategic": "Estratégico",
}

_EN_TIER_LABELS = {
    "all": "All",
    "long_tail": "Long tail",
    "scaled": "Scaled",
    "core": "Core",
    "strategic": "Strategic",
}

_RANKING_COLUMNS = [
    "seller_key",
    "seller_state",
    "seller_volume_tier",
    "seller_order_count",
    "avg_ticket",
    "estimated_revenue",
    "delay_rate",
    "avg_delivery_time_days",
    "avg_review_score",
]


def _load_seller_slice() -> pd.DataFrame:
    if not SELLER_SLICE_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(SELLER_SLICE_PATH)


def _display_tier(value: object) -> str:
    technical_value = str(value)
    return _TIER_LABELS.get(
        technical_value, technical_value.replace("_", " ").capitalize()
    )


def _display_filter_value(value: object) -> str:
    return "Todos" if str(value) == "all" else str(value)


def _format_integer(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _format_decimal(value: float, decimal_places: int) -> str:
    formatted = f"{value:,.{decimal_places}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _format_currency(value: int | float) -> str:
    return f"R$ {_format_decimal(float(value), 2)}"


def _format_percentage(value: int | float) -> str:
    if pd.isna(value):
        return "Indisponível"
    return f"{_format_decimal(float(value) * 100, 1)}%"


def _format_delivery_days(value: int | float) -> str:
    if pd.isna(value):
        return "Indisponível"
    return f"{_format_decimal(float(value), 1)} dias"


def _format_review_score(value: int | float) -> str:
    return _format_decimal(float(value), 2)


def _build_executive_ranking(ranking: pd.DataFrame) -> pd.DataFrame:
    executive = ranking.copy()
    executive["seller_display"] = executive["seller_key"].map(
        lambda value: f"Seller • {str(value)[-8:]}"
    )
    executive["seller_volume_tier"] = executive["seller_volume_tier"].map(_display_tier)
    executive["avg_ticket"] = executive["avg_ticket"].map(_format_currency)
    executive["estimated_revenue"] = executive["estimated_revenue"].map(
        _format_currency
    )
    executive["delay_rate"] = executive["delay_rate"].map(_format_percentage)
    executive["avg_delivery_time_days"] = executive["avg_delivery_time_days"].map(
        _format_delivery_days
    )
    executive["avg_review_score"] = executive["avg_review_score"].map(
        _format_review_score
    )
    return executive[
        [
            "seller_display",
            "seller_state",
            "seller_volume_tier",
            "seller_order_count",
            "avg_ticket",
            "estimated_revenue",
            "delay_rate",
            "avg_delivery_time_days",
            "avg_review_score",
        ]
    ].rename(
        columns={
            "seller_display": "Seller",
            "seller_state": "Estado",
            "seller_volume_tier": "Faixa de volume",
            "seller_order_count": "Pedidos",
            "avg_ticket": "Ticket médio",
            "estimated_revenue": "Receita estimada",
            "delay_rate": "Taxa de atraso",
            "avg_delivery_time_days": "Entrega média",
            "avg_review_score": "Avaliação média",
        }
    )


def render_seller_performance(locale: Locale, df: pd.DataFrame | None = None) -> None:
    is_en = locale == LOCALE_EN_US
    st.title("Seller Performance" if is_en else "Desempenho de Sellers")
    st.markdown(
        "Compare order volumes, delivery performance, and seller contribution."
        if is_en
        else "Visão de volume de pedidos, desempenho de entrega e contribuição dos sellers."
    )
    st.caption(
        "Compare sellers by volume tier and state."
        if is_en
        else "Compare sellers por faixa de volume e estado."
    )
    st.markdown("### How to read this page" if is_en else "### Como interpretar esta página")
    st.write(
        "Use the filters to compare sellers by volume and location. "
        "The metrics show order concentration, delivery performance, and seller contribution."
        if is_en
        else "Use os filtros para comparar grupos de sellers por volume e localização. "
        "Os indicadores ajudam a identificar concentração de pedidos, comportamento "
        "logístico e contribuição estimada."
    )

    public_mode = is_public_visitor_mode()
    if public_mode:
        if df is not None and not df.empty and not valid_item_grain(df):
            st.warning(
                "Seller performance is unavailable because order-item keys are invalid."
                if is_en
                else "Desempenho indisponível: o grão pedido × item não é válido."
            )
            return
        seller_df = (
            build_seller_slice(df, observed_delivery_only=True)
            if df is not None and not df.empty
            else pd.DataFrame()
        )
    else:
        seller_df = _load_seller_slice()
    if seller_df.empty:
        st.info(
            "Seller data is unavailable in this environment."
            if is_en
            else "Dados de sellers não disponíveis neste ambiente."
        )
        st.caption(
            "This view requires the seller slice produced by the governed pipeline."
            if is_en
            else "A visualização depende do slice semântico de sellers gerado em uma "
            "execução controlada."
        )
        return

    tier_options = ["all"] + sorted(
        str(value) for value in seller_df["seller_volume_tier"].dropna().unique()
    )
    state_options = ["all"] + sorted(
        str(value) for value in seller_df["seller_state"].dropna().unique()
    )

    f1, f2 = st.columns(2)
    selected_tier = f1.selectbox(
        "Volume tier" if is_en else "Faixa de volume",
        options=tier_options,
        format_func=lambda value: _EN_TIER_LABELS.get(value, value)
        if is_en
        else _display_tier(value),
        key="seller_perf_tier_filter",
    )
    selected_state = f2.selectbox(
        "State" if is_en else "Estado",
        options=state_options,
        format_func=lambda value: ("All" if value == "all" else value)
        if is_en
        else _display_filter_value(value),
        key="seller_perf_state_filter",
    )

    filtered = seller_df.copy()
    if selected_tier != "all":
        filtered = filtered[filtered["seller_volume_tier"] == selected_tier]
    if selected_state != "all":
        filtered = filtered[filtered["seller_state"] == selected_state]

    if filtered.empty:
        st.warning(
            "No sellers match the selected filters."
            if is_en
            else "Nenhum seller encontrado para os filtros selecionados."
        )
        return

    seller_count = int(filtered["seller_key"].nunique())
    order_count = int(
        pd.to_numeric(filtered["seller_order_count"], errors="coerce").fillna(0).sum()
    )
    if public_mode and df is not None:
        order_count = filtered_seller_order_count(df, filtered)

    avg_delay_rate = float(pd.to_numeric(filtered["delay_rate"], errors="coerce").mean())
    avg_delivery_days = float(
        pd.to_numeric(filtered["avg_delivery_time_days"], errors="coerce").mean()
    )
    delay_display = _format_percentage(avg_delay_rate)
    delivery_display = _format_delivery_days(avg_delivery_days)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Active sellers" if is_en else "Sellers ativos", _format_integer(seller_count))
    m2.metric(
        ("Unique orders" if public_mode else "Orders per seller (sum)")
        if is_en
        else ("Pedidos únicos" if public_mode else "Pedidos por seller (soma)"),
        _format_integer(order_count),
    )
    m3.metric("Average late delivery rate" if is_en else "Taxa média de atraso", delay_display)
    m4.metric(
        "Average delivery time" if is_en else "Tempo médio de entrega",
        delivery_display,
    )

    st.markdown("### Leitura executiva")
    st.caption(
        "A taxa de atraso e o tempo de entrega dão o mesmo peso a cada seller da seleção."
    )
    if public_mode:
        st.caption(
            "Por seller, o atraso usa itens com entrega realizada e data prevista. "
            "O prazo médio usa itens com duração registrada."
        )
    else:
        st.caption("A soma por seller pode contar o mesmo pedido em mais de um seller.")
    st.markdown(
        f"- A seleção atual reúne **{_format_integer(seller_count)} sellers** e "
        f"**{_format_integer(order_count)} pedidos**.\n"
        f"- Taxa média de atraso **{delay_display}**.\n"
        f"- Tempo médio de entrega **{delivery_display}**."
    )

    chart_left, chart_right = st.columns(2)
    with chart_left:
        tier_dist = (
            filtered["seller_volume_tier"]
            .astype(str)
            .value_counts()
            .rename_axis("seller_volume_tier")
            .reset_index(name="count")
        )
        display_tier_dist = tier_dist.assign(
            tier_label=tier_dist["seller_volume_tier"].map(_display_tier)
        )
        fig_tier = px.bar(
            display_tier_dist,
            x="count",
            y="tier_label",
            color="tier_label",
            orientation="h",
            title="Distribuição de sellers por faixa de volume",
            labels={
                "count": "Quantidade de sellers",
                "tier_label": "Faixa de volume",
            },
            hover_data={"seller_volume_tier": True, "tier_label": False},
        )
        fig_tier.update_layout(showlegend=False, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_tier, width="stretch")

    with chart_right:
        sla = (
            filtered.groupby("seller_volume_tier", dropna=False)
            .agg(
                avg_delay_rate=("delay_rate", "mean"),
                avg_delivery_days=("avg_delivery_time_days", "mean"),
            )
            .reset_index()
        )
        sla["avg_delay_rate"] = sla["avg_delay_rate"] * 100
        display_sla = sla.assign(
            tier_label=sla["seller_volume_tier"].map(_display_tier)
        )
        if public_mode and sla["avg_delay_rate"].isna().all():
            st.markdown("#### Atrasos por faixa de volume")
            st.info("A seleção não tem entregas com datas suficientes para comparar atrasos.")
        elif (
            public_mode
            and sla["avg_delay_rate"].notna().all()
            and sla["avg_delay_rate"].eq(0).all()
        ):
            st.markdown("#### Atrasos por faixa de volume")
            st.info("Nenhum atraso registrado nas faixas da seleção.")
        else:
            _render_delay_by_tier(display_sla)

    _render_seller_ranking(filtered)


def _render_delay_by_tier(display_sla: pd.DataFrame) -> None:
    fig_sla = px.bar(
        display_sla,
        x="avg_delay_rate",
        y="tier_label",
        color="avg_delay_rate",
        orientation="h",
        title="Taxa média de atraso por faixa de volume",
        labels={
            "avg_delay_rate": "Taxa média de atraso (%)",
            "tier_label": "Faixa de volume",
        },
        hover_data={"seller_volume_tier": True, "tier_label": False},
    )
    fig_sla.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig_sla, width="stretch")


def _render_seller_ranking(filtered: pd.DataFrame) -> None:
    ranking = filtered.copy()
    exact_gmv = "gross_item_value" in ranking
    if exact_gmv:
        ranking["estimated_revenue"] = ranking["gross_item_value"]
    else:
        ranking["estimated_revenue"] = pd.to_numeric(
            ranking["avg_ticket"], errors="coerce"
        ).fillna(0) * pd.to_numeric(
            ranking["seller_order_count"], errors="coerce"
        ).fillna(0)
    ranking = ranking.sort_values("estimated_revenue", ascending=False).head(20)

    technical_ranking = ranking[_RANKING_COLUMNS].copy()
    executive_ranking = _build_executive_ranking(technical_ranking)

    if exact_gmv:
        technical_ranking = technical_ranking.rename(
            columns={"estimated_revenue": "gross_item_value"}
        )
        executive_ranking = executive_ranking.rename(
            columns={
                "Receita estimada": "GMV (R$)",
                "Ticket médio": "Valor médio por item",
            }
        )
        st.markdown("### Top sellers por GMV")
        st.caption(
            "GMV = soma dos valores dos itens e do frete. Atraso e entrega são médias por grupo de seller."
        )
    else:
        st.markdown("### Top Sellers por Receita Estimada")
        st.caption(
            "Estimativa do recorte histórico: valor médio por item × pedidos por seller."
        )
    st.dataframe(
        executive_ranking,
        width="stretch",
        hide_index=True,
    )

    with st.expander("Detalhes técnicos dos sellers", expanded=False):
        st.dataframe(technical_ranking, width="stretch", hide_index=True)
