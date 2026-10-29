import copy

import pytest
import yaml

from blastguard_ai.checks import run_checks
from blastguard_ai.manifest import ManifestError, MAX_MANIFEST_BYTES, parse_manifest


def rules(text_or_docs):
    docs = parse_manifest(text_or_docs) if isinstance(text_or_docs, str) else text_or_docs
    return {f.rule_id for f in run_checks(docs)}


@pytest.fixture
def good(hardened):
    return parse_manifest(hardened)


def container(docs):
    return docs[0]["spec"]["template"]["spec"]["containers"][0]


def podspec(docs):
    return docs[0]["spec"]["template"]["spec"]


def test_hardened_manifest_is_clean(good):
    assert rules(good) == set()


@pytest.mark.parametrize("rule,mutate", [
    ("BG001", lambda d: container(d)["securityContext"].update(privileged=True)),
    ("BG002", lambda d: podspec(d).update(volumes=[{"name": "h", "hostPath": {"path": "/"}}])),
    ("BG003", lambda d: podspec(d).update(hostNetwork=True)),
    ("BG004", lambda d: podspec(d).update(hostPID=True)),
    ("BG004", lambda d: podspec(d).update(hostIPC=True)),
    ("BG005", lambda d: podspec(d)["securityContext"].pop("runAsNonRoot")),
    ("BG005", lambda d: container(d)["securityContext"].update(runAsUser=0)),
    ("BG006", lambda d: container(d)["securityContext"].pop("allowPrivilegeEscalation")),
    ("BG006", lambda d: container(d)["securityContext"].update(allowPrivilegeEscalation=True)),
    ("BG007", lambda d: container(d)["resources"]["limits"].pop("memory")),
    ("BG007", lambda d: container(d).pop("resources")),
    ("BG008", lambda d: container(d).update(image="nginx:latest")),
    ("BG008", lambda d: container(d).update(image="nginx")),
    ("BG008", lambda d: container(d).update(image="registry:5000/team/app")),
    ("BG009", lambda d: container(d)["securityContext"].pop("readOnlyRootFilesystem")),
    ("BG010", lambda d: container(d)["securityContext"]["capabilities"].update(add=["SYS_ADMIN"])),
    ("BG010", lambda d: container(d)["securityContext"]["capabilities"].update(add=["all"])),
    ("BG011", lambda d: podspec(d).pop("automountServiceAccountToken")),
    ("BG013", lambda d: d.pop(1)),
])
def test_rule_positive(good, rule, mutate):
    d = copy.deepcopy(good)
    mutate(d)
    assert rule in rules(d)


@pytest.mark.parametrize("rule,mutate", [
    ("BG001", lambda d: container(d)["securityContext"].update(privileged=False)),
    ("BG002", lambda d: podspec(d).update(volumes=[{"name": "t", "emptyDir": {}}])),
    ("BG003", lambda d: podspec(d).update(hostNetwork=False)),
    ("BG008", lambda d: container(d).update(image="nginx@sha256:" + "a" * 64)),
    ("BG008", lambda d: container(d).update(image="registry:5000/team/app:1.2.3")),
    ("BG010", lambda d: container(d)["securityContext"]["capabilities"].update(add=["NET_BIND_SERVICE"])),
    ("BG005", lambda d: (podspec(d)["securityContext"].clear(),
                         container(d)["securityContext"].update(runAsNonRoot=True))),
])
def test_rule_negative(good, rule, mutate):
    d = copy.deepcopy(good)
    mutate(d)
    assert rule not in rules(d)


def test_loadbalancer_positive_and_negative():
    svc = {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "s"},
           "spec": {"type": "LoadBalancer", "ports": [{"port": 80}]}}
    assert "BG012" in rules([svc])
    svc["spec"]["type"] = "ClusterIP"
    assert "BG012" not in rules([svc])
    assert "BG013" not in rules([svc])  # no workload -> no netpol note


def test_cronjob_and_pod_supported():
    pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "p"},
           "spec": {"containers": [{"name": "c", "image": "busybox", "securityContext": {"privileged": True}}]}}
    cj = {"apiVersion": "batch/v1", "kind": "CronJob", "metadata": {"name": "j"},
          "spec": {"schedule": "* * * * *", "jobTemplate": {"spec": {"template": {"spec": pod["spec"]}}}}}
    assert "BG001" in rules([pod]) and "BG001" in rules([cj])


def test_init_containers_checked(good):
    d = copy.deepcopy(good)
    podspec(d)["initContainers"] = [{"name": "init", "image": "busybox:latest"}]
    assert "BG008" in rules(d)


def test_samples_are_blocked(samples):
    assert len(samples) >= 3
    expected = {"01-privileged-hostpath.yaml": {"BG001", "BG002", "BG004", "BG010"},
                "02-latest-root-nolimits.yaml": {"BG005", "BG007", "BG008"},
                "03-loadbalancer-exposed.yaml": {"BG003", "BG008", "BG012"},
                "04-stateless-api-missing-limits.yaml": {"BG006", "BG007", "BG011"}}
    for name, text in samples.items():
        assert expected[name] <= rules(text), name


@pytest.mark.parametrize("bad", ["", "   \n", "a: [unclosed", "- just\n- a list\n", "kind: Pod\n",
                                 "apiVersion: v1\nkind: Pod\nmetadata: {}\n", None, 42, "---\n---\n"])
def test_parse_fail_closed(bad):
    with pytest.raises(ManifestError):
        parse_manifest(bad)


def test_oversized_rejected(hardened):
    with pytest.raises(ManifestError):
        parse_manifest(hardened + "#" * (MAX_MANIFEST_BYTES + 1))


def test_unsafe_yaml_tags_rejected():
    with pytest.raises(ManifestError):
        parse_manifest("apiVersion: v1\nkind: Pod\nmetadata: {name: x}\nx: !!python/object/apply:os.system ['id']\n")
