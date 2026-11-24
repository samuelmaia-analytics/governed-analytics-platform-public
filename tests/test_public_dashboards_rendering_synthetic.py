from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _run(script: str) -> AppTest:
    app = AppTest.from_string(script, default_timeout=60).run()
    assert not app.exception
    return app


def test_dashboard_revenue_renders_with_synthetic_fixture():
    _run(
        """
import streamlit as st
from scripts.generate_synthetic_public_demo import generate
from app.pages.revenue_analytics import render_revenue_analytics

df = generate(rows=5001)
render_revenue_analytics(df, 'pt-BR')
"""
    )


def test_dashboard_sellers_renders_with_synthetic_fixture():
    _run(
        """
import streamlit as st
from scripts.generate_synthetic_public_demo import generate
from app.pages.seller_performance import render_seller_performance

df = generate(rows=5001)
render_seller_performance('pt-BR', df=df)
"""
    )


def test_dashboard_cohorts_renders_with_synthetic_fixture():
    _run(
        """
import streamlit as st
from scripts.generate_synthetic_public_demo import generate
from app.pages.cohort_retention import render_cohort_retention

df = generate(rows=5001)
render_cohort_retention('pt-BR', df=df)
"""
    )


def test_dashboard_eda_renders_with_synthetic_fixture():
    _run(
        """
import streamlit as st
from scripts.generate_synthetic_public_demo import generate
from app.pages.eda import render_eda

df = generate(rows=5001)
render_eda(df, 'pt-BR')
"""
    )


def test_dashboard_quality_and_governance_renders_with_synthetic_fixture():
    _run(
        """
import streamlit as st
from scripts.generate_synthetic_public_demo import generate
from app.pages.data_quality import render_data_quality
from app.pages.governance_control_center import render_governance_control_center
from app.context import _build_context_from_dataframe

df = generate(rows=5001)
context = _build_context_from_dataframe(df, docs_dir='docs', uses_persisted_governance=False)

render_data_quality(context.quality_results, context.quality_table, 'pt-BR')
render_governance_control_center(df, context.classification_df, context.risk_result, context.quality_results, 'pt-BR')
"""
    )
