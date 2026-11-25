"""Documented capabilities exposed by the public visitor profile."""

from __future__ import annotations

import streamlit as st

from app.components.ui import PUBLIC_REPOSITORY
from app.i18n import LOCALE_EN_US, Locale


def render_public_automation(locale: Locale) -> None:
    is_en = locale == LOCALE_EN_US
    st.title("Automation and orchestration" if is_en else "Automação e Orquestração")
    st.caption(
        "Architecture of the versioned n8n templates."
        if is_en
        else "Arquitetura dos templates n8n versionados."
    )
    st.subheader("Declared execution flow" if is_en else "Fluxo de execução declarado")
    schedule, validation, success, error = (
        (
            "Scheduled input check",
            "Governance checks",
            "Execution log and alert",
            "Error log and alert",
        )
        if is_en
        else (
            "Verificação agendada da origem",
            "Checks de governança",
            "Log de execução e alerta",
            "Log de erro e alerta",
        )
    )
    st.graphviz_chart(
        f'''
        digraph {{
            node [shape=box, style=rounded];
            input [label="{schedule}"];
            checks [label="{validation}"];
            completed [label="{success}"];
            failed [label="{error}"];
            input -> checks -> completed;
            checks -> failed [style=dashed];
        }}
        ''',
        alt=f"{schedule} → {validation} → {success} / {error}",
    )
    steps = (
        (
            (
                "1. Schedule and input",
                "Every 24 h the template sets execution metadata and checks the configured input.",
            ),
            (
                "2. Validation and documentation",
                "Python runs quality checks, LGPD classification and risk scoring, then generates governance reports in the controlled checkout.",
            ),
            (
                "3. Logs and alerts",
                "Success registers the execution and sends a configured Discord notification. The error workflow extracts failure metadata, registers the error and sends its own alert.",
            ),
        )
        if is_en
        else (
            (
                "1. Agendamento e origem",
                "A cada 24 h, o template prepara os metadados e verifica a origem configurada.",
            ),
            (
                "2. Validação e documentação",
                "O Python executa checks de qualidade, classificação LGPD e cálculo de risco, depois gera relatórios de governança no checkout controlado.",
            ),
            (
                "3. Logs e alertas",
                "No sucesso, registra a execução e envia o alerta configurado no Discord. O fluxo de erro extrai metadados da falha, registra o erro e envia seu próprio alerta.",
            ),
        )
    )
    for column, (label, description) in zip(st.columns(3), steps, strict=True):
        with column, st.container(border=True):
            st.markdown(f"**{label}**")
            st.write(description)
    st.info(
        "These templates declare no retry queue or webhook. Execution, logs and alerts require a controlled n8n environment."
        if is_en
        else "Os templates não configuram fila, retentativas ou webhook. Execução, logs e alertas exigem um ambiente n8n controlado."
    )
    st.link_button(
        "Template documentation" if is_en else "Documentação dos templates",
        f"{PUBLIC_REPOSITORY}/tree/main/workflows/n8n",
    )


def render_public_snowflake(locale: Locale) -> None:
    is_en = locale == LOCALE_EN_US
    st.title("Snowflake Integration" if is_en else "Integração Snowflake")
    st.write(
        "An on-demand connector and explorer inspect metadata and query existing tables in a configured Snowflake environment."
        if is_en
        else "O projeto implementa um conector e um explorador sob demanda para consultar metadados e tabelas existentes em um ambiente Snowflake configurado."
    )
    st.subheader("Integration boundary" if is_en else "Limites da integração")
    st.markdown(
        """
- **Origin and destination** — Snowflake tables supply query results to the controlled explorer.
- **Transformations and quality** — The GAP pipeline prepares Bronze, Silver and Gold and evaluates contracts separately. Explorer queries do not materialize these layers or replace quality checks.
- **Access** — Account, role, warehouse and authentication come from the controlled environment. Data access follows that role.
"""
        if is_en
        else """
- **Origem e destino** — tabelas existentes no Snowflake fornecem resultados ao explorador controlado.
- **Transformações e qualidade** — o pipeline do GAP prepara Bronze, Silver e Gold e avalia contratos separadamente. Consultas do explorador não materializam essas camadas nem substituem os checks.
- **Acesso** — conta, role, warehouse e autenticação vêm do ambiente controlado. O acesso aos dados segue as permissões da role.
"""
    )
    st.info(
        "Connections and queries are unavailable in the public profile."
        if is_en
        else "Conexões e consultas estão indisponíveis no perfil público."
    )
