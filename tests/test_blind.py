"""Blind suite: cases parse, oracles accept originals, and reject a hand-made function-breaking patch (no network)."""
import json
from pathlib import Path

import pytest
import yaml

from benchmark.blind.oracles import ORACLES, evaluate

BLIND = Path(__file__).resolve().parent.parent / "benchmark" / "blind"
CASES = json.loads((BLIND / "cases.json").read_text())


def _pod(d):
    return d["spec"]["jobTemplate"]["spec"]["template"]["spec"] if d["kind"] == "CronJob" else d["spec"]["template"]["spec"]


def _break_b01(ds):
    _pod(ds[0])["securityContext"] = {"runAsNonRoot": True, "runAsUser": 1000, "fsGroup": 1000}


def _break_b02(ds):
    p = _pod(ds[0]); p.pop("hostAliases"); p["securityContext"] = {"runAsNonRoot": True}


def _break_b03(ds):
    p = _pod(ds[0]); p["containers"][1]["securityContext"] = {"runAsUser": 2000, "capabilities": {"drop": ["ALL"]}}
    p["containers"][0]["securityContext"] = {"runAsUser": 101}


def _break_b04(ds):
    _pod(ds[0]).pop("initContainers")


def _break_b05(ds):
    _pod(ds[0])["automountServiceAccountToken"] = False


def _break_b06(ds):
    ds[0]["spec"]["template"]["spec"]["containers"][0]["resources"] = {"limits": {"memory": "512Mi", "cpu": "500m"}}


BREAKS = {"b01": _break_b01, "b02": _break_b02, "b03": _break_b03, "b04": _break_b04, "b05": _break_b05, "b06": _break_b06}


def test_six_cases_with_oracles():
    assert len(CASES) == 6 and {c["id"] for c in CASES} == set(ORACLES)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_case_parses_and_original_preserved(case):
    text = (BLIND / case["file"]).read_text()
    assert [d for d in yaml.safe_load_all(text) if d]
    r = evaluate(ORACLES[case["id"]], text, text)
    assert r["verdict"] == "preserved", r


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_breaking_patch_detected(case):
    text = (BLIND / case["file"]).read_text()
    ds = [d for d in yaml.safe_load_all(text) if d]
    BREAKS[case["id"][:3]](ds)
    r = evaluate(ORACLES[case["id"]], text, yaml.safe_dump_all(ds))
    assert r["verdict"] == "broken" and r["failed"], r


def test_no_patch_and_garbage():
    spec = ORACLES["b01-postgres-statefulset"]
    assert evaluate(spec, "", None)["verdict"] == "no_patch"
    assert evaluate(spec, "", "a: [")["verdict"] == "broken"


def test_oracles_do_not_import_gate():
    assert "blastguard_ai" not in (BLIND / "oracles.py").read_text().replace("does not import blastguard_ai", "")
