from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_app_starts_against_supplied_csvs_without_exceptions():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Home Energy Model"
    assert app.radio[0].options == ["Historical view", "System model"]
    app.radio[0].set_value("System model").run()
    assert not app.exception
