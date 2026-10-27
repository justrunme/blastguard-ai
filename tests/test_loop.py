"""Loop tests use TEST-ONLY scripted fake clients (tests/fakes.py). No real model output here."""
import pytest

from blastguard_ai.llm import LLMError, extract_from_content, build_user_prompt
from blastguard_ai.loop import BLOCKED, UNRESOLVED, VERIFIED, run_remediation
from blastguard_ai.report import to_json, to_markdown
from fakes import ErrorFakeClient, ScriptedFakeClient

SAMPLE = "02-latest-root-nolimits.yaml"


@pytest.fixture(autouse=True, params=["builtin-only", "with-external"])
def ext(request, monkeypatch):
    if request.param == "builtin-only":
        monkeypatch.setenv("BLASTGUARD_DISABLE_EXTERNAL", "1")
    return request.param


def test_fixed_on_first_attempt(samples, hardened):
    c = ScriptedFakeClient([hardened])
    r = run_remediation(samples[SAMPLE], c)
    assert (r.initial_status, r.status, len(r.attempts)) == (BLOCKED, VERIFIED, 1)
    assert r.final_yaml == hardened and "+          image: nginx:1.27.2" in r.diff
    assert '"final_status": "VERIFIED"' in to_json(r) and "BLOCKED -> VERIFIED" in to_markdown(r)


def test_garbage_then_fix_uses_feedback(samples, hardened):
    c = ScriptedFakeClient(["not: [valid", None, hardened])
    r = run_remediation(samples[SAMPLE], c)
    assert r.status == VERIFIED and len(r.attempts) == 3
    assert c.calls[1]["feedback"] and "rejected" in c.calls[1]["feedback"][0]


def test_garbage_three_times_unresolved(samples):
    r = run_remediation(samples[SAMPLE], ScriptedFakeClient(["garbage text", "{{{", ""]))
    assert r.status == UNRESOLVED and r.final_yaml is None and r.diff == ""


def test_delete_workload_is_not_verified(samples):
    only_netpol = ("apiVersion: networking.k8s.io/v1\nkind: NetworkPolicy\nmetadata: {name: x, namespace: payments}\n"
                   "spec: {podSelector: {}}\n")
    r = run_remediation(samples[SAMPLE], ScriptedFakeClient([only_netpol] * 3))
    assert r.status == UNRESOLVED
    assert any("removed" in g for g in r.attempts[0]["verification"]["guard"])


def test_unchanged_patch_unresolved(samples):
    r = run_remediation(samples[SAMPLE], ScriptedFakeClient([samples[SAMPLE]] * 3))
    assert r.status == UNRESOLVED and r.attempts[-1]["verification"]["findings"]


def test_api_error_unresolved(samples):
    r = run_remediation(samples[SAMPLE], ErrorFakeClient())
    assert r.status == UNRESOLVED and "API error" in r.error and len(r.attempts) == 1


def test_no_client_stays_blocked(samples):
    r = run_remediation(samples[SAMPLE], None)
    assert r.status == BLOCKED and not r.attempts


@pytest.mark.parametrize("bad", ["", "x: [", "#" * 70000])
def test_bad_input_unresolved_without_llm_call(bad):
    c = ScriptedFakeClient([])
    r = run_remediation(bad, c)
    assert r.status == UNRESOLVED and not c.calls


def test_clean_input_needs_no_llm(hardened):
    c = ScriptedFakeClient([])
    r = run_remediation(hardened, c)
    assert r.status == VERIFIED and not c.calls and not r.attempts


def test_attempt_cap(samples):
    c = ScriptedFakeClient(["x"] * 10)
    r = run_remediation(samples[SAMPLE], c, max_attempts=99)
    assert len(c.calls) == 3 and r.status == UNRESOLVED


def test_wall_time_cap(samples):
    r = run_remediation(samples[SAMPLE], ScriptedFakeClient(["x"] * 3), max_wall_s=-1)
    assert r.status == UNRESOLVED and r.error == "wall-time budget exhausted" and not r.attempts


def test_extract_and_prompt():
    assert extract_from_content("hi\n```yaml\na: 1\n```\n") == "a: 1\n"
    assert extract_from_content("no code") is None
    p = build_user_prompt("a: 1", [{"rule_id": "BG001", "severity": "critical", "object": "o",
                                    "container": "c", "message": "m"}], ["fix x"])
    assert "BG001" in p and "rejected" in p


def test_real_client_requires_key(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    from blastguard_ai.llm import NebiusClient
    with pytest.raises(LLMError):
        NebiusClient()
