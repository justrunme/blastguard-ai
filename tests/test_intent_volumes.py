"""Red-team tests: non-hostPath volume sources replaced or removed (hand-written manifests)."""
import pytest
import yaml

from blastguard_ai.intent import HIGH, NO_HIGH_IMPACT_DRIFT, REVIEW_REQUIRED, intent_report
from blastguard_ai.manifest import parse_manifest

SOURCES = {
    "persistentVolumeClaim": {"claimName": "data-pvc"},
    "configMap": {"name": "app-config"},
    "secret": {"secretName": "app-secret"},
    "projected": {"sources": [{"configMap": {"name": "app-config"}}]},
    "nfs": {"server": "nfs.local", "path": "/export"},
    "csi": {"driver": "csi.example.com"},
}


def base(source="persistentVolumeClaim", read_only=False):
    mount = {"name": "data", "mountPath": "/data"}
    if read_only:
        mount["readOnly"] = True
    return {
        "apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "app", "namespace": "ns"},
        "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "app"}}, "template": {
            "metadata": {"labels": {"app": "app"}},
            "spec": {"containers": [{"name": "c", "image": "nginx:1.27.2", "volumeMounts": [mount]}],
                     "volumes": [{"name": "data", source: dict(SOURCES.get(source, {}))}]}}},
    }


def ps(d):
    return d["spec"]["template"]["spec"]


def report(o, n):
    return intent_report(parse_manifest(yaml.safe_dump(o)), parse_manifest(yaml.safe_dump(n)))


def high_codes(r):
    return {d["code"] for d in r["drifts"] if d["severity"] == HIGH}


@pytest.mark.parametrize("source", sorted(SOURCES))
def test_source_replaced_by_emptydir_is_high(source):
    n = base(source)
    ps(n)["volumes"] = [{"name": "data", "emptyDir": {}}]
    r = report(base(source), n)
    assert r["verdict"] == REVIEW_REQUIRED
    assert high_codes(r) & {"PERSISTENT_VOLUME_REPLACED", "CONFIG_VOLUME_REPLACED"}


def test_pvc_volume_removed_mount_kept_is_high():
    n = base()
    ps(n)["volumes"] = []
    r = report(base(), n)
    assert r["verdict"] == REVIEW_REQUIRED
    assert "VOLUME_REMOVED" in high_codes(r)


def test_pvc_volume_and_mount_removed_is_high():
    n = base()
    ps(n)["volumes"] = []
    ps(n)["containers"][0]["volumeMounts"] = []
    r = report(base(), n)
    assert r["verdict"] == REVIEW_REQUIRED
    assert "VOLUME_REMOVED" in high_codes(r)


def test_pvc_claim_changed_is_high():
    n = base()
    ps(n)["volumes"][0]["persistentVolumeClaim"]["claimName"] = "other"
    assert report(base(), n)["verdict"] == REVIEW_REQUIRED


# --- negative controls: must NOT raise high drift ---

def test_emptydir_stays_emptydir():
    o = base()
    ps(o)["volumes"] = [{"name": "data", "emptyDir": {}}]
    n = base()
    ps(n)["volumes"] = [{"name": "data", "emptyDir": {"sizeLimit": "1Gi"}}]
    assert report(o, n)["verdict"] == NO_HIGH_IMPACT_DRIFT


@pytest.mark.parametrize("source", sorted(SOURCES))
def test_source_unchanged(source):
    assert report(base(source), base(source))["verdict"] == NO_HIGH_IMPACT_DRIFT


def test_additive_tmp_emptydir():
    n = base()
    ps(n)["volumes"].append({"name": "tmp", "emptyDir": {}})
    ps(n)["containers"][0]["volumeMounts"].append({"name": "tmp", "mountPath": "/tmp"})
    r = report(base(), n)
    assert r["verdict"] == NO_HIGH_IMPACT_DRIFT and not high_codes(r)


def test_readonly_config_mount_added():
    n = base("configMap", read_only=True)
    r = report(base("configMap"), n)
    assert not high_codes(r)


def test_additive_readonly_mount():
    n = base()
    ps(n)["volumes"].append({"name": "cfg", "configMap": {"name": "x"}})
    ps(n)["containers"][0]["volumeMounts"].append({"name": "cfg", "mountPath": "/etc/x", "readOnly": True})
    assert report(base(), n)["verdict"] == NO_HIGH_IMPACT_DRIFT
