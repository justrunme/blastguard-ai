"""Smoke test for the UI. Without a key the run button is disabled; no model call happens."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_renders_without_key(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert at.button[0].disabled
    at.selectbox[0].select("01-privileged-hostpath").run()
    assert "privileged: true" in at.text_area[0].value
