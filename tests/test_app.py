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


def test_app_renders_release_decision_for_a_stored_result(monkeypatch):
    import json
    from fakes import ScriptedFakeClient
    from blastguard_ai.loop import run_remediation
    root = Path(APP).parent
    ev = json.loads((root / "examples/01-privileged-hostpath.evidence.json").read_text())
    res = run_remediation((root / "samples/01-privileged-hostpath.yaml").read_text(),
                          ScriptedFakeClient([ev["final_yaml"]]))
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["result"] = res
    at.run()
    assert not at.exception
    page = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    assert "REVIEW_REQUIRED" in page and "human must review" in page
