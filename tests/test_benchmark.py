"""Benchmark corpus and oracle tests (no network)."""
import copy
import json
from pathlib import Path

import pytest
import yaml

from benchmark.oracles import ORACLES, evaluate, load_docs

BENCH = Path(__file__).resolve().parent.parent / "benchmark"
CASES = json.loads((BENCH / "cases.json").read_text())
VALID = [c for c in CASES if not ORACLES[c["id"]].get("invalid_input")]


def text(cid):
    return (BENCH / next(c["file"] for c in CASES if c["id"] == cid)).read_text()


def test_corpus_shape():
    assert len(CASES) == 16
    cats = [c["category"] for c in CASES]
    assert cats.count("function-critical") == 5 and cats.count("fixable") == 6
    assert cats.count("hardened") == 2 and cats.count("hostile") == 3
    assert set(ORACLES) == {c["id"] for c in CASES}
    for c in CASES:
        assert (BENCH / c["file"]).read_text().startswith("# CASE")


def test_oracles_do_not_import_intent_gate():
    src = (BENCH / "oracles.py").read_text()
    assert "blastguard_ai" not in src.split('"""', 2)[2]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_case_file_loads(case):
    t = (BENCH / case["file"]).read_text()
    if case["id"] == "14-malformed-yaml":
        with pytest.raises(yaml.YAMLError):
            load_docs(t)
    else:
        docs = load_docs(t)
        assert docs
        if case["id"] == "16-not-kubernetes":
            assert "kind" not in docs[0]


@pytest.mark.parametrize("case", VALID, ids=lambda c: c["id"])
def test_oracle_preserved_on_original(case):
    t = text(case["id"])
    r = evaluate(ORACLES[case["id"]], t, t)
    assert r["verdict"] == "preserved", r["failed"]


def _mutate(cid, fn):
    docs = load_docs(text(cid))
    fn(docs)
    return yaml.safe_dump_all(docs)


def _ps(d):
    return d["spec"]["template"]["spec"]


BREAKS = {
    "01-hostpath-log-collector": lambda ds: _ps(ds[0])["volumes"].__setitem__(0, {"name": "varlog", "emptyDir": {}}),
    "02-hostnetwork-node-exporter": lambda ds: _ps(ds[0]).__setitem__("hostNetwork", False),
    "03-public-loadbalancer": lambda ds: ds[1]["spec"].__setitem__("type", "ClusterIP"),
    "04-ebpf-net-admin": lambda ds: _ps(ds[0])["containers"][0]["securityContext"]["capabilities"].__setitem__(
        "add", ["BPF"]),
    "05-docker-socket": lambda ds: _ps(ds[0]).__setitem__("volumes", [{"name": "docker-sock", "emptyDir": {}}]),
    "06-missing-limits": lambda ds: _ps(ds[0])["containers"][0].__setitem__(
        "resources", {"limits": {"cpu": "100m", "memory": "16Mi"}}),
    "09-root-with-tmp": lambda ds: (_ps(ds[0])["containers"][0].__setitem__(
        "securityContext", {"readOnlyRootFilesystem": True}),
        _ps(ds[0])["containers"][0]["volumeMounts"].pop()),
    "10-multidoc-deploy-service": lambda ds: ds.append({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
        "metadata": {"name": "deny", "namespace": "shop"},
        "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}}),
    "11-no-securitycontext-emptydir": lambda ds: _ps(ds[0])["containers"][0].__setitem__("args", ["--save", "60 1"]),
    "15-prompt-injection": lambda ds: _ps(ds[0])["containers"][0].__setitem__("securityContext", {"privileged": True}),
}


@pytest.mark.parametrize("cid", sorted(BREAKS))
def test_oracle_detects_function_breaking_patch(cid):
    r = evaluate(ORACLES[cid], text(cid), _mutate(cid, BREAKS[cid]))
    assert r["verdict"] == "broken"


def test_oracle_accepts_conservative_fix():
    def fix(ds):
        c = _ps(ds[0])["containers"][0]
        c["resources"] = {"limits": {"cpu": "200m", "memory": "128Mi"}}
    assert evaluate(ORACLES["06-missing-limits"], text("06-missing-limits"),
                    _mutate("06-missing-limits", fix))["verdict"] == "preserved"


def test_unparsable_patch_is_broken_and_none_is_no_patch():
    t = text("06-missing-limits")
    assert evaluate(ORACLES["06-missing-limits"], t, "a: [")["verdict"] == "broken"
    assert evaluate(ORACLES["06-missing-limits"], t, None)["verdict"] == "no_patch"
