from __future__ import annotations

import streamlit as st

from app.components.ui import PUBLIC_REPOSITORY
from app.i18n import LOCALE_EN_US, Locale


def render_about(locale: Locale) -> None:
    is_en = locale == LOCALE_EN_US
    st.title("About the project" if is_en else "Sobre o projeto")
    st.write(
        "GAP is an independent portfolio project. Its public demo uses synthetic data "
        "to demonstrate how quality and publication controls reduce the risk of analysis based on incomplete data or unauthorized distribution."
        if is_en
        else "O GAP é um projeto independente de portfólio sobre operação de marketplace. "
        "A experiência pública usa uma amostra sintética para demonstrar análises de receita, sellers e retenção com controles de qualidade e publicação."
    )
    st.header("Architecture and validation" if is_en else "Arquitetura e validação")
    st.write(
        "Python and DuckDB support local processing, Parquet stores artifacts, and "
        "Streamlit and Plotly present the analyses. The architecture documents Bronze, "
        "Silver, Gold and Quarantine, along with the semantic layer and data contracts."
        if is_en
        else "Python e DuckDB apoiam o processamento local, Parquet armazena artefatos, "
        "e Streamlit e Plotly apresentam as análises. A arquitetura documenta Bronze, "
        "Silver, Gold e Quarantine, além da camada semântica e dos contratos de dados."
    )
    st.subheader(
        "From ingestion to publication" if is_en else "Da ingestão à publicação"
    )
    st.markdown(
        """
1. **Bronze** preserves input for traceability; **Silver** standardizes data and applies contracts.
2. **Quarantine** isolates invalid records. **Gold** provides validated facts for joins and aggregation.
3. The **semantic layer** computes GMV, orders and cohort retention. The **Publication Gate** evaluates release evidence, separately from the authorization to distribute exact bytes.
"""
        if is_en
        else """
1. **Bronze** preserva as entradas para rastreabilidade; **Silver** padroniza os dados e aplica contratos.
2. **Quarantine** isola registros inválidos. **Gold** disponibiliza fatos validados para junções e agregações.
3. A **camada semântica** calcula GMV, pedidos e retenção. O **Publication Gate** avalia evidências de liberação, separadamente da autorização de distribuição dos bytes.
"""
    )
    st.markdown(
        f"- [{'Layers and quarantine' if is_en else 'Camadas e quarentena'}]"
        f"({PUBLIC_REPOSITORY}/blob/main/docs/architecture/local_data_lake.md)\n"
        f"- [{'Semantic layer' if is_en else 'Camada semântica'}]"
        f"({PUBLIC_REPOSITORY}/blob/main/docs/architecture/semantic_layer.md)\n"
        f"- [{'Data contracts' if is_en else 'Contratos de dados'}]"
        f"({PUBLIC_REPOSITORY}/blob/main/docs/data_contracts.md)\n"
        f"- [{'Public scope' if is_en else 'Escopo público'}]"
        f"({PUBLIC_REPOSITORY}/blob/main/docs/governance/public_scope.md)\n"
        f"- [{'CI and policy validation' if is_en else 'CI e validação de políticas'}]"
        f"({PUBLIC_REPOSITORY}/actions)"
    )
    st.header("Developer" if is_en else "Sobre o desenvolvedor")
    st.write(
        "Samuel Maia — Data Engineer II at Avanade. He develops GAP independently for his portfolio, outside Avanade's product portfolio."
        if is_en
        else "Samuel Maia — Engenheiro de Dados Pleno na Avanade. Ele desenvolve o GAP de forma independente para seu portfólio pessoal, fora do catálogo de produtos da Avanade."
    )
    st.link_button("GitHub", PUBLIC_REPOSITORY, icon=":material/code:")
    st.link_button(
        "Professional portfolio" if is_en else "Portfólio profissional",
        "https://samuelmaia-analytics.com.br",
        icon=":material/person:",
    )
