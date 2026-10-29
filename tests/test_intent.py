"""Intent Preservation Gate tests. Inputs are hand-written manifests, not model output, except the regression
test that replays the real Nemotron patches saved in examples/."""
import copy
import json
from pathlib import Path

import pytest
import yaml

from blastguard_ai.intent import NO_HIGH_IMPACT_DRIFT, REVIEW_REQUIRED, intent_report
from blastguard_ai.loop import VERIFIED, run_remediation
from blastguard_ai.manifest import parse_manifest
from fakes import ScriptedFakeClient

ROOT = Path(__file__).resolve().parent.parent

DEPLOY = """
apiVersion: apps/v1
kind: Deployment
metadata: {name: app, namespace: ns}
spec:
  replicas: 2
  selector: {matchLabels: {app: app}}
  template:
    metadata: {labels: {app: app}}
    spec:
      containers:
        - name: c
          image: nginx:1.27.2
          command: ["nginx"]
          env: [{name: A, value: "1"}]
          ports: [{containerPort: 8080}]
          volumeMounts: [{name: data, mountPath: /data}]
      volumes:
        - name: data
          hostPath: {path: /var/data}
"""
SVC = """
apiVersion: v1
kind: Service
metadata: {name: svc, namespace: ns}
spec:
  type: LoadBalancer
  selector: {app: app}
  ports: [{port: 80, targetPort: 8080}]
"""


def docs(text):
    return parse_manifest(text)


def mutate(text, fn):
    ds = list(yaml.safe_load_all(text))
    fn(ds[0])
    return parse_manifest(yaml.safe_dump_all(ds))


def codes(report):
    return {d["code"] for d in report["drifts"]}


def test_identical_manifest_has_no_drift():
    r = intent_report(docs(DEPLOY), docs(DEPLOY))
    assert r["verdict"] == NO_HIGH_IMPACT_DRIFT and r["drifts"] == []


def test_hostpath_replaced_by_emptydir_requires_review():
    new = mutate(DEPLOY, lambda d: d["spec"]["template"]["spec"]["volumes"].__setitem__(0, {"name": "data", "emptyDir": {}}))
    r = intent_report(docs(DEPLOY), new)
    assert r["verdict"] == REVIEW_REQUIRED and "HOSTPATH_REPLACED" in codes(r)


def test_hostpath_volume_removed_requires_review():
    def f(d):
        d["spec"]["template"]["spec"]["volumes"] = []
        d["spec"]["template"]["spec"]["containers"][0]["volumeMounts"] = []
    r = intent_report(docs(DEPLOY), mutate(DEPLOY, f))
    assert {"HOSTPATH_REMOVED", "MOUNT_REMOVED"} <= codes(r) and r["verdict"] == REVIEW_REQUIRED


def test_hostpath_kept_with_other_path_is_flagged():
    new = mutate(DEPLOY, lambda d: d["spec"]["template"]["spec"]["volumes"][0]["hostPath"].update(path="/other"))
    assert "HOSTPATH_CHANGED" in codes(intent_report(docs(DEPLOY), new))


def test_loadbalancer_to_clusterip_requires_review():
    new = mutate(SVC, lambda d: d["spec"].update(type="ClusterIP"))
    r = intent_report(docs(SVC), new)
    assert r["verdict"] == REVIEW_REQUIRED and "SERVICE_EXPOSURE_CHANGED" in codes(r)


def test_service_unchanged_or_clusterip_origin_is_clean():
    assert intent_report(docs(SVC), docs(SVC))["verdict"] == NO_HIGH_IMPACT_DRIFT
    cip = mutate(SVC, lambda d: d["spec"].update(type="ClusterIP"))
    assert intent_report(cip, cip)["drifts"] == []


@pytest.mark.parametrize("fn,code", [
    (lambda d: d["spec"]["template"]["spec"]["containers"][0].update(command=["sh"]), "COMMAND_CHANGED"),
    (lambda d: d["spec"]["template"]["spec"]["containers"][0].pop("env"), "ENV_CHANGED"),
    (lambda d: d["spec"]["template"]["spec"]["containers"][0].update(ports=[]), "PORTS_REMOVED"),
    (lambda d: d["spec"].update(replicas=1), "REPLICAS_CHANGED"),
])
def test_other_high_impact_changes(fn, code):
    r = intent_report(docs(DEPLOY), mutate(DEPLOY, fn))
    assert code in codes(r) and r["verdict"] == REVIEW_REQUIRED


def test_security_only_hardening_is_not_high_impact():
    def f(d):
        c = d["spec"]["template"]["spec"]["containers"][0]
        c["securityContext"] = {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}
        c["resources"] = {"limits": {"cpu": "1", "memory": "1Gi"}}
    r = intent_report(docs(DEPLOY), mutate(DEPLOY, f))
    assert r["verdict"] == NO_HIGH_IMPACT_DRIFT and codes(r) == {"LIMITS_ADDED"}


def test_privileged_removal_is_high_but_caps_drop_alone_is_not():
    priv = mutate(DEPLOY, lambda d: d["spec"]["template"]["spec"]["containers"][0].update(securityContext={"privileged": True}))
    r = intent_report(priv, mutate(DEPLOY, lambda d: None))
    assert "PRIVILEGED_REMOVED" in codes(r) and r["verdict"] == REVIEW_REQUIRED


def test_readonly_rootfs_without_writable_mount_is_medium_and_not_gating():
    base = mutate(DEPLOY, lambda d: d["spec"]["template"]["spec"].update(volumes=[]) or
                  d["spec"]["template"]["spec"]["containers"][0].update(volumeMounts=[]))
    new = mutate(DEPLOY, lambda d: d["spec"]["template"]["spec"].update(volumes=[]) or
                 d["spec"]["template"]["spec"]["containers"][0].update(volumeMounts=[], securityContext={"readOnlyRootFilesystem": True}))
    r = intent_report(base, new)
    assert "ROOTFS_READONLY_NO_WRITABLE_PATH" in codes(r) and r["verdict"] == NO_HIGH_IMPACT_DRIFT


def test_gate_fails_closed_on_malformed_structure():
    bad = docs(DEPLOY)
    bad[0]["spec"]["template"]["spec"]["containers"][0]["ports"] = {"not": "a list"}
    ok = docs(DEPLOY)
    r = intent_report(ok, bad)
    assert r["verdict"] in (REVIEW_REQUIRED, NO_HIGH_IMPACT_DRIFT)  # must not raise
    boom = intent_report(None, bad)  # type: ignore[arg-type]
    assert boom["verdict"] == REVIEW_REQUIRED and boom["error"]


def test_removed_objects_are_left_to_identity_guard():
    assert intent_report(docs(DEPLOY + "---" + SVC), docs(DEPLOY))["drifts"] == []


@pytest.mark.parametrize("sample,verdict", [
    ("01-privileged-hostpath", REVIEW_REQUIRED),
    ("02-latest-root-nolimits", NO_HIGH_IMPACT_DRIFT),
    ("03-loadbalancer-exposed", REVIEW_REQUIRED),
])
def test_real_nemotron_patches_in_examples(sample, verdict):
    ev = json.loads((ROOT / "examples" / f"{sample}.evidence.json").read_text())
    r = intent_report(docs((ROOT / "samples" / f"{sample}.yaml").read_text()), docs(ev["final_yaml"]))
    assert r["verdict"] == verdict


def test_loop_reports_review_required_release(samples):
    sample = "01-privileged-hostpath.yaml"
    ev = json.loads((ROOT / "examples" / "01-privileged-hostpath.evidence.json").read_text())
    res = run_remediation(samples[sample], ScriptedFakeClient([ev["final_yaml"]]))
    assert res.status == VERIFIED and res.release == "REVIEW_REQUIRED"
    assert res.intent["verdict"] == REVIEW_REQUIRED
    assert "Intent Preservation Gate" in __import__("blastguard_ai.report", fromlist=["x"]).to_markdown(res)


def test_unverified_run_has_no_intent_and_is_not_proposed(samples):
    res = run_remediation(samples["01-privileged-hostpath.yaml"], ScriptedFakeClient(["garbage"] * 3))
    assert res.intent is None and res.release == "NOT_PROPOSED"
