from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from app.i18n import LOCALE_EN_US, Locale
from src.artifact_access import dataset_download
from src.governance_types import PrivacyRiskResult
from src.privacy_transformations import apply_privacy_actions

_RISK_LEVEL_LABELS = {
    "low": "BAIXO",
    "medium": "MÉDIO",
    "high": "ALTO",
}

_PUBLICATION_RECOMMENDATION_LABELS = {
    "approved": "APROVADO",
    "needs_review": "REVISÃO NECESSÁRIA",
    "blocked": "BLOQUEADO",
}

_RECOMMENDATION_LABELS = {
    "Apply masking for direct identifiers in shared datasets.": (
        "Aplicar mascaramento aos identificadores diretos em datasets compartilhados."
    ),
    "Anonymize or remove sensitive columns from executive layers.": (
        "Anonimizar ou remover colunas sensíveis das camadas executivas."
    ),
    "Review null patterns in critical personal-data columns.": (
        "Revisar padrões de valores nulos em colunas críticas de dados pessoais."
    ),
    "Document legal basis and retention policy for personal data usage.": (
        "Documentar a base legal e a política de retenção para uso de dados pessoais."
    ),
    "Block publication until masking/anonymization controls are implemented.": (
        "Bloquear a publicação até que os controles de mascaramento ou "
        "anonimização estejam implementados."
    ),
}


def _display_label(value: object, labels: dict[str, str]) -> str:
    raw_value = str(value)
    return labels.get(raw_value.lower(), raw_value.upper())


def _display_recommendation(recommendation: str) -> str:
    return _RECOMMENDATION_LABELS.get(recommendation, recommendation)


def render_lgpd_privacy_risk(
    df: pd.DataFrame,
    classification_df: pd.DataFrame,
    risk_result: PrivacyRiskResult,
    locale: Locale,
) -> None:
    is_en = locale == LOCALE_EN_US
    st.title("LGPD Privacy and Controls" if is_en else "Privacidade e Controles LGPD")
    st.markdown(
        "Explore privacy risks, data classifications, and the controls applied by the analytics pipeline."
        if is_en
        else "Visão demonstrativa dos riscos de privacidade, classificações de dados "
        "e controles aplicados ao pipeline analítico."
    )
    st.caption(
        "These indicators assess the demonstration scenario. A legal assessment or a formal "
        "data protection impact report is a separate process."
        if is_en
        else "Os indicadores abaixo representam uma avaliação diagnóstica do cenário "
        "demonstrativo e não substituem uma análise jurídica ou RIPD formal."
    )
    st.markdown("### How to read this page" if is_en else "### Como interpretar esta página")
    st.write(
        "See how the platform classifies personal and sensitive data, scores privacy risk, "
        "and recommends controls before publication."
        if is_en
        else "A página demonstra como a plataforma identifica dados pessoais e "
        "sensíveis, calcula risco de privacidade e aplica recomendações de "
        "governança antes da publicação analítica."
    )

    tab_risk, tab_classification, tab_preview = st.tabs(
        [
            "Risk score" if is_en else "Score e risco",
            "Classifications" if is_en else "Classificações",
            "Transformation preview" if is_en else "Prévia de transformações",
        ]
    )

    with tab_risk:
        st.subheader("Privacy risk assessment" if is_en else "Avaliação diagnóstica de privacidade")
        st.info(
            "This scenario shows how the platform flags elevated risk and may recommend "
            "blocking publication when the assessment has yet to account for protective controls."
            if is_en
            else "O cenário demonstrativo evidencia como a plataforma identifica "
            "riscos elevados e pode recomendar bloqueio de publicação quando "
            "controles de proteção ainda não estão considerados na avaliação."
        )
        col1, col2 = st.columns(2)
        with col1:
            st.metric(
                "Privacy risk score" if is_en else "Score de risco de privacidade",
                f"{risk_result['score']} / 100",
            )
        with col2:
            st.metric(
                "Risk level" if is_en else "Nível de risco",
                risk_result["risk_level"].upper()
                if is_en
                else _display_label(risk_result["risk_level"], _RISK_LEVEL_LABELS),
            )
        recommendation = risk_result.get("publication_recommendation", "needs_review")
        st.metric(
            "Publication recommendation" if is_en else "Recomendação de publicação",
            recommendation.replace("_", " ").upper()
            if is_en
            else _display_label(recommendation, _PUBLICATION_RECOMMENDATION_LABELS),
        )

        components = risk_result.get("score_components", {})
        if components:
            with st.expander(
                "Score components" if is_en else "Componentes técnicos do score",
                expanded=False,
            ):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {"component": key, "points": value}
                            for key, value in components.items()
                        ]
                    ),
                    width="stretch",
                )

        st.markdown("**Recommendations**" if is_en else "**Recomendações**")
        for rec in risk_result["recommendations"]:
            st.write(f"- {rec if is_en else _display_recommendation(rec)}")

    with tab_classification:
        class_counts = (
            classification_df["lgpd_classification"].value_counts().reset_index()
        )
        class_counts.columns = ["classification", "count"]
        st.bar_chart(class_counts.set_index("classification"))
        st.dataframe(classification_df, width="stretch")

    with tab_preview:
        st.info(
            "Visualize exactly how masking/anonymization will affect the shared dataset."
            if is_en
            else "Visualize exatamente como mascaramento/anonimização afetam o dataset compartilhado."
        )
        transformed_df, metadata_df = apply_privacy_actions(df, classification_df)

        left, right = st.columns(2)
        left.metric(
            "Original Shape" if is_en else "Shape Original",
            f"{df.shape[0]} x {df.shape[1]}",
        )
        right.metric(
            "Transformed Shape" if is_en else "Shape Transformado",
            f"{transformed_df.shape[0]} x {transformed_df.shape[1]}",
        )

        inner_tab1, inner_tab2, inner_tab3 = st.tabs(
            [
                "Resumo de Ações / Actions Summary",
                "Metadados / Metadata",
                "Dataset Protegido / Protected Dataset",
            ]
        )

        with inner_tab1:
            if metadata_df.empty:
                st.info(
                    "No privacy actions were applied."
                    if is_en
                    else "Nenhuma ação de privacidade foi aplicada."
                )
            else:
                actions_summary = (
                    metadata_df["action"]
                    .value_counts()
                    .rename_axis("action")
                    .reset_index(name="count")
                )
                st.dataframe(actions_summary, width="stretch")

        with inner_tab2:
            st.dataframe(metadata_df, width="stretch")

        with inner_tab3:
            csv_bytes = transformed_df.to_csv(index=False).encode("utf-8")
            source_bytes = df.to_csv(index=False).encode("utf-8")
            authorized_bytes = dataset_download(
                csv_bytes,
                dataset=str(df.attrs.get("dataset_name", "governance_preview")),
                version=hashlib.sha256(source_bytes).hexdigest(),
                risk_recommendation=risk_result.get(
                    "publication_recommendation", "needs_review"
                ),
                uses_persisted_governance=bool(
                    df.attrs.get("uses_persisted_governance", False)
                ),
            )
            if authorized_bytes is None:
                st.info(
                    "Preview and download require explicit publication authorization."
                    if is_en
                    else "Prévia e download exigem autorização explícita de publicação."
                )
            else:
                st.dataframe(transformed_df.head(50), width="stretch")
                st.download_button(
                    label="Download Protected CSV" if is_en else "Baixar CSV Protegido",
                    data=authorized_bytes,
                    file_name="protected_dataset_preview.csv",
                    mime="text/csv",
                )
