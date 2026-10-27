import copy

from blastguard_ai.guard import identity_violations, image_repo
from blastguard_ai.manifest import parse_manifest


def test_image_repo():
    assert image_repo("nginx:latest") == image_repo("nginx:1.27") == "nginx"
    assert image_repo("reg:5000/a/b:1") == "reg:5000/a/b"
    assert image_repo("a/b@sha256:abc") == "a/b"


def test_identity_ok(hardened):
    d = parse_manifest(hardened)
    assert identity_violations(d, copy.deepcopy(d)) == []


def test_deleted_workload(hardened):
    d = parse_manifest(hardened)
    assert any("removed" in e for e in identity_violations(d, d[1:]))


def test_renamed_swapped_scaled(hardened):
    d = parse_manifest(hardened)
    p = copy.deepcopy(d)
    p[0]["spec"]["template"]["spec"]["containers"][0]["image"] = "busybox:1.36"
    p[0]["spec"]["replicas"] = 0
    errs = identity_violations(d, p)
    assert any("image repo changed" in e for e in errs) and any("replicas" in e for e in errs)
    p2 = copy.deepcopy(d)
    p2[0]["spec"]["template"]["spec"]["containers"] = []
    assert any("container 'api' was removed" in e for e in identity_violations(d, p2))
    p3 = copy.deepcopy(d)
    p3[0]["metadata"]["name"] = "other"
    assert identity_violations(d, p3)


def test_unexpected_new_kind(hardened):
    d = parse_manifest(hardened)
    extra = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "x"}}
    assert any("unexpected" in e for e in identity_violations(d, d + [extra]))
