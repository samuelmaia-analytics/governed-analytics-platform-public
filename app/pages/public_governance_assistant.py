from __future__ import annotations

import time

import streamlit as st

from app.i18n import LOCALE_EN_US, Locale
from src.governance_rag import LocalIndex, RagError, split_document
from src.public_governance_rag import (
    MAX_QUESTION_CHARS,
    SOURCE_VERSION,
    load_public_sources,
    retrieve_public_evidence,
)

SUGGESTIONS = {
    "pt-BR": (
        "O que define um contrato de dados?",
        "O que significa uma pontuação de qualidade 100/100?",
        "Qual é a responsabilidade de Bronze, Silver e Gold?",
        "Quais registros a quarentena isola?",
        "Como a LGPD orienta a minimização de dados pessoais?",
        "O que o Publication Gate verifica na autorização de distribuição?",
    ),
    "en-US": (
        "What does a data contract define?",
        "What does a quality score of 100/100 mean?",
        "What are the responsibilities of Bronze, Silver and Gold?",
        "Which invalid records does quarantine isolate?",
        "How does LGPD guide personal data minimization?",
        "How does the Publication Gate use distribution authorization?",
    ),
}


@st.cache_resource(show_spinner=False, max_entries=2)
def _public_index(sources: tuple[tuple[str, str, str], ...]) -> LocalIndex:
    return LocalIndex(
        tuple(
            chunk
            for path, digest, text in sources
            for chunk in split_document(text, source=path, sha256=digest)
        )
    )


def render_public_governance_assistant(locale: Locale) -> None:
    is_en = locale == LOCALE_EN_US
    st.write(
        "Search the approved bilingual documentation. TF-IDF ranks and quotes excerpts. Retrieval runs locally without a generative model."
        if is_en
        else "Consulte a documentação bilíngue autorizada. O TF-IDF classifica e cita trechos. A recuperação é local e funciona sem modelo generativo."
    )
    try:
        sources = load_public_sources()
    except RagError:
        st.warning(
            "Public sources are unavailable. Try again later."
            if is_en
            else "As fontes públicas estão indisponíveis. Tente novamente mais tarde."
        )
        return

    st.caption(
        f"{len(sources)} approved sources. Use a topic question without personal data or credentials."
        if is_en
        else f"{len(sources)} fontes autorizadas. Faça uma pergunta sobre o tema, sem incluir dados pessoais ou credenciais."
    )
    with st.form("public_governance_question", clear_on_submit=True):
        example = st.selectbox(
            "Suggested questions" if is_en else "Sugestões de perguntas",
            SUGGESTIONS[locale],
            index=None,
            placeholder="Choose an example" if is_en else "Escolha uma sugestão",
        )
        question = st.text_area(
            "Your question" if is_en else "Sua pergunta",
            max_chars=MAX_QUESTION_CHARS,
            help=(
                "Your own question takes precedence over the suggestion."
                if is_en
                else "Se preencher este campo, sua pergunta terá prioridade sobre a sugestão."
            ),
        )
        submitted = st.form_submit_button(
            "Find evidence" if is_en else "Buscar evidências"
        )
    if not submitted:
        return
    question = question.strip() or example or ""
    if not question:
        st.info(
            "Enter a question or select an example."
            if is_en
            else "Digite uma pergunta ou escolha uma sugestão."
        )
        return
    now = time.monotonic()
    if now - st.session_state.get("_public_rag_last_query", float("-inf")) < 2:
        st.info(
            "Wait two seconds between searches."
            if is_en
            else "Aguarde dois segundos entre as consultas."
        )
        return
    st.session_state["_public_rag_last_query"] = now

    try:
        with st.spinner("Searching sources..." if is_en else "Buscando nas fontes..."):
            hits = retrieve_public_evidence(_public_index(sources), question)
    except RagError:
        st.warning(
            "Use a short question without personal data, credentials or links."
            if is_en
            else "Use uma pergunta curta, sem dados pessoais, credenciais ou links."
        )
        return
    if not hits:
        st.info(
            "Insufficient evidence in the approved public sources."
            if is_en
            else "Não há evidência suficiente nas fontes públicas autorizadas."
        )
        return
    st.subheader(
        "Evidence from public sources" if is_en else "Evidências das fontes públicas"
    )
    for hit in hits:
        chunk = hit.chunk
        lines = "lines" if is_en else "linhas"
        version = "version" if is_en else "versão"
        with st.expander(
            f"[{hit.citation}] {chunk.source.rsplit('/', 1)[-1]}", expanded=True
        ):
            st.caption(
                f"{chunk.source} · {lines} {chunk.start_line}–{chunk.end_line} · {version} {SOURCE_VERSION}"
            )
            st.code(chunk.text, language="text", wrap_lines=True)
            st.code(f"SHA-256 {chunk.sha256}", language="text", wrap_lines=True)
