from __future__ import annotations

import streamlit as st

PUBLIC_REPOSITORY = (
    "https://github.com/samuelmaia-analytics/governed-analytics-platform-public"
)

_BASE_CSS = """
<style>
.gap-hero {
  --gap-hero-ink: #f3f7ff;
  --gap-hero-muted: #c4d4e8;
  --gap-hero-accent: #79e2ef;
  background: linear-gradient(125deg, #101e33, #162f4a 70%, #16445a);
  color: var(--gap-hero-ink);
  border: 1px solid #46718d;
  border-radius: 18px;
  padding: clamp(1.25rem, 5vw, 3.25rem);
  margin-block: 0.25rem 0.75rem;
}
.gap-hero h1 {
  color: var(--gap-hero-ink);
  font-size: clamp(2rem, 5vw, 3.75rem);
  line-height: 1.08;
  letter-spacing: -0.035em;
  padding: 0;
  margin: 0.6rem 0;
}
.gap-hero p {
  color: var(--gap-hero-muted);
  max-width: 62ch;
  margin: 0.75rem 0 0;
}
.gap-hero .gap-kicker {
  color: var(--gap-hero-accent);
  font-size: 0.82rem;
  font-weight: 650;
  letter-spacing: 0.075em;
  text-transform: uppercase;
}
.gap-hero .gap-lead {
  color: var(--gap-hero-ink);
  font-size: clamp(1.05rem, 2vw, 1.35rem);
  font-weight: 600;
}
</style>
"""


def inject_base_styles() -> None:
    st.markdown(_BASE_CSS, unsafe_allow_html=True)


def render_footer(*, locale: str) -> None:
    label = (
        "Independent portfolio project by Samuel Maia"
        if locale == "en-US"
        else "Projeto independente de portfólio de Samuel Maia"
    )
    st.divider()
    st.caption(f"{label} · [GitHub]({PUBLIC_REPOSITORY})")
