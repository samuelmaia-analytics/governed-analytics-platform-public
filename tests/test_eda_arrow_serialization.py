from datetime import date

import pandas as pd
import pyarrow as pa

from app.pages.eda import _present_descriptive_statistics
from src.eda import descriptive_statistics


def test_descriptive_tables_serialize_nullable_counts_in_both_locales():
    data = pd.DataFrame(
        {
            "identifier": ["001", "001", None],
            "amount": [1.5, 2.5, None],
            "date": [date(2025, 1, 1), date(2025, 1, 1), None],
            "time": pd.to_datetime(
                ["2025-01-01T00:00:00Z", "2025-01-03T00:00:00Z", None]
            ),
        }
    )
    summary = descriptive_statistics(data)
    technical = pa.Table.from_pandas(summary)
    english = pa.Table.from_pandas(_present_descriptive_statistics(summary, "en-US"))
    portuguese = pa.Table.from_pandas(_present_descriptive_statistics(summary, "pt-BR"))

    assert technical["unique"].type == pa.int64()
    assert technical["unique"].to_pylist() == english["unique"].to_pylist()
    assert portuguese["Únicos"].to_pylist() == [1, None, 1, None]
    assert technical["count"].to_pylist() == [2, 2, 2, 2]
    assert technical["freq"].to_pylist() == [2, None, 2, None]
    assert technical["top"].to_pylist() == ["001", None, "2025-01-01", None]
    assert technical["mean"].to_pylist() == [None, 2.0, None, None]
    assert portuguese["Média (temporal)"].to_pylist() == [
        None,
        None,
        None,
        "2025-01-02 00:00:00+00:00",
    ]
