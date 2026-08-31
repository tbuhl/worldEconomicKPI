import pandas as pd

from world_kpi.ui import line_chart


def test_full_history_chart_includes_crisis_markers() -> None:
    series = pd.Series(
        range(40),
        index=pd.date_range("1990-01-01", periods=40, freq="YS"),
    )
    figure = line_chart(series, "Long history", "index", years=None)
    annotation_text = {annotation.text for annotation in figure.layout.annotations}
    assert {"Dot-com peak", "GFC build-up", "Lehman"}.issubset(annotation_text)
    assert len(figure.layout.shapes) >= 3

