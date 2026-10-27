import pytest

from blastguard_ai import validators


def test_not_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(validators, "BIN_DIR", tmp_path)
    monkeypatch.setattr(validators.shutil, "which", lambda _: None)
    f = tmp_path / "m.yaml"
    f.write_text("a: 1")
    assert validators.run_kubeconform(f).status == "not_installed"
    assert validators.run_kube_linter(f).status == "not_installed"


@pytest.mark.skipif(not validators._find("kube-linter"), reason="kube-linter not installed")
def test_kube_linter_real(tmp_path, hardened, samples):
    f = tmp_path / "m.yaml"
    f.write_text(samples["02-latest-root-nolimits.yaml"])
    bad = validators.run_kube_linter(f)
    assert bad.status == "fail" and any("latest-tag" in i for i in bad.issues)
    f.write_text(hardened)
    assert validators.run_kube_linter(f).status == "pass"


@pytest.mark.skipif(not validators._find("kubeconform"), reason="kubeconform not installed")
def test_kubeconform_real(tmp_path, hardened):
    f = tmp_path / "m.yaml"
    f.write_text(hardened)
    r = validators.run_kubeconform(f)
    if r.status == "error":
        pytest.skip(f"schemas unavailable: {r.detail}")
    assert r.status == "pass"
    f.write_text(hardened.replace("replicas: 2", "replicas: two"))
    assert validators.run_kubeconform(f).status == "fail"
