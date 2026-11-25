from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from app import context
from app.pages import genai_insights, publication_governance


@pytest.mark.parametrize("flag", ["GAP_PUBLIC_VISITOR_MODE", "GAP_PUBLIC_DEMO_MODE"])
def test_toml_boolean_enables_public_profile_before_loading_data(monkeypatch, flag):
    monkeypatch.setenv("GAP_PUBLIC_VISITOR_MODE", "false")
    monkeypatch.setenv("GAP_PUBLIC_DEMO_MODE", "false")
    monkeypatch.setattr(context, "st", SimpleNamespace(secrets={flag: True}))
    monkeypatch.setattr(context, "_load_platform_dataframe", lambda path: path)
    context.configure_public_profile()
    assert context.load_input_dataframe("pt-BR") == context.DEFAULT_PUBLIC_DEMO_DATASET


@pytest.mark.parametrize(
    ("module", "renderer", "blocked_calls"),
    [
        (genai_insights, "render_genai_insights('pt-BR')", ("_load_genai_features",)),
        (
            publication_governance,
            "render_publication_governance()",
            ("load_publication_governance_snapshot",),
        ),
    ],
)
def test_public_routes_do_not_load_controlled_artifacts(
    monkeypatch, module, renderer, blocked_calls
):
    monkeypatch.setenv("GAP_PUBLIC_VISITOR_MODE", "true")
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("RAG_EXTERNAL_ENABLED", "true")
    for name in blocked_calls:
        monkeypatch.setattr(
            module,
            name,
            lambda *_args, **_kwargs: pytest.fail("Controlled path reached"),
        )
    app = AppTest.from_string(
        f"from {module.__name__} import {renderer.split('(')[0]}\n{renderer}"
    ).run()
    assert not app.exception
    assert (
        not app.text_area
        and not app.radio
        and not app.checkbox
        and not app.download_button
    )
    assert app.markdown


def test_public_governance_displays_actual_blocked_gate_despite_passed_checks(
    monkeypatch,
):
    monkeypatch.setenv("GAP_PUBLIC_VISITOR_MODE", "true")
    app = AppTest.from_string(
        "from app.pages.publication_governance import render_publication_governance\n"
        "from src.publication_gate import evaluate_operational_publication_gate\n"
        "gate = evaluate_operational_publication_gate(total_checks=1, pass_checks=1,"
        " warn_checks=0, fail_checks=0, critical_failures=0, public_authorization_complete=False)\n"
        "render_publication_governance(public_gate=gate)"
    ).run()
    assert not app.exception
    assert [(metric.label, metric.value) for metric in app.metric] == [
        ("Decisão operacional", "Bloqueado"),
        ("Checks aprovados", "1/1"),
        ("Checks reprovados", "0"),
    ]


def test_quality_with_no_nulls_keeps_evidence_without_empty_null_chart(monkeypatch):
    chart = Mock()
    monkeypatch.setattr(st, "altair_chart", chart)
    app = AppTest.from_string(
        "import pandas as pd\n"
        "from app.pages.data_quality import render_data_quality\n"
        "render_data_quality({'failed_checks_count': 0, 'total_rows': 2, 'total_columns': 1,"
        " 'null_pct_by_column': {'item': 0.0}}, pd.DataFrame({'status': ['PASS']}), 'pt-BR')"
    ).run()
    assert not app.exception
    assert any("Nenhum valor nulo" in item.value for item in app.info)
    chart.assert_called_once()
    assert app.dataframe[0].value.to_dict("records") == [
        {"Campo": "item", "Nulos (%)": 0.0}
    ]
