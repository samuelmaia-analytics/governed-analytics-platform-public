"""Regression for EDA category controls on small synthetic datasets."""

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("count", [1, 2, 5, 6])
def test_small_category_analysis_renders(count):
    app = AppTest.from_string(
        "import pandas as pd\n"
        "from app.pages.eda import _render_column_analysis\n"
        f"frame = pd.DataFrame({{'category': [f'scenario-{{i}}' for i in range({count})]}})\n"
        "_render_column_analysis(frame, 'en-US')\n"
    ).run(timeout=20)
    assert not app.exception
    assert len(app.slider) == (1 if count > 5 else 0)


def test_empty_category_analysis_renders():
    app = AppTest.from_string(
        "import pandas as pd\n"
        "from app.pages.eda import _render_column_analysis\n"
        "_render_column_analysis(pd.DataFrame({'category': pd.Series(dtype='object')}), 'en-US')\n"
    ).run(timeout=20)
    assert not app.exception
    assert not app.slider


def test_category_selection_and_slider_remain_interactive():
    app = AppTest.from_string(
        "import pandas as pd\n"
        "from app.pages.eda import _render_column_analysis\n"
        "frame = pd.DataFrame({'many': [f'scenario-{i}' for i in range(8)], 'single': ['scenario-only'] * 8})\n"
        "_render_column_analysis(frame, 'en-US')\n"
    ).run(timeout=20)
    app.slider[0].set_value(5).run()
    assert not app.exception
    assert app.slider[0].value == 5
    app.selectbox[0].select("single").run()
    assert not app.exception
    assert not app.slider
    app.selectbox[0].select("many").run()
    assert not app.exception
    assert len(app.slider) == 1
