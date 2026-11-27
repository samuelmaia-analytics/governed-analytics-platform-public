"""Public Streamlit reference views with text fallback and no download action."""

import base64

import streamlit as st

from src.streamlit_architecture_view import read_architecture_view

_NAMES = {"azure": "Azure", "aws": "AWS"}


def render_public_architecture(provider: str) -> None:
    name = _NAMES[provider]
    description = (
        f"{name} reference proposal. Batch data passes through landing and curated "
        "layers, then through the Publication Gate. Approved data may reach the "
        "consumption layer. Failed checks or blocked data lead to Quarantine."
    )
    st.title(f"{name} Reference Architecture")
    with st.expander("AS-IS · Local implementation"):
        st.write(
            "The local pipeline uses Python, SQL, dbt and DuckDB with quality, privacy and publication checks."
        )
    st.subheader("TO-BE · Proposed cloud architecture")
    svg = read_architecture_view(provider)
    if svg is None:
        st.info("Diagram unavailable for this session.")
    else:
        encoded = base64.b64encode(svg).decode("ascii")
        st.markdown(
            f'<img src="data:image/svg+xml;base64,{encoded}" alt="{description}" style="max-width:100%">',
            unsafe_allow_html=True,
        )
    with st.expander("Accessible text alternative"):
        st.write(description)
