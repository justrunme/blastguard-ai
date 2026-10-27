"""Optional external validators (kubeconform, kube-linter), run as static binaries on a sandbox file.

Only the manifest file is passed to them; no LLM output is ever executed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"

KUBE_LINTER_CHECKS = [
    "privileged-container", "privilege-escalation-container", "run-as-non-root",
    "no-read-only-root-fs", "host-network", "host-pid", "host-ipc", "latest-tag",
    "unset-cpu-requirements", "unset-memory-requirements", "sensitive-host-mounts",
    "docker-sock", "writable-host-mount", "unsafe-proc-mount",
]


@dataclass
class ValidatorResult:
    name: str
    status: str  # pass | fail | error | not_installed
    issues: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def failed(self) -> bool:
        return self.status == "fail"

    def to_dict(self) -> dict:
        return asdict(self)


def _find(binary: str) -> str | None:
    local = BIN_DIR / binary
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return shutil.which(binary)


def run_kubeconform(path: Path, timeout: int = 60) -> ValidatorResult:
    exe = _find("kubeconform")
    if not exe:
        return ValidatorResult("kubeconform", "not_installed")
    cache = Path(os.environ.get("KUBECONFORM_CACHE", "/tmp/kubeconform-cache"))
    cache.mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run([exe, "-strict", "-summary", "-output", "json", "-cache", str(cache), str(path)],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return ValidatorResult("kubeconform", "error", detail="timeout")
    try:
        data = json.loads(p.stdout or "{}")
    except json.JSONDecodeError:
        return ValidatorResult("kubeconform", "error", detail=(p.stderr or p.stdout)[:300])
    issues, errored = [], []
    for res in data.get("resources", []):
        st = res.get("status")
        line = f"{res.get('kind')}/{res.get('name')}: {res.get('msg', '')}"
        if st == "statusInvalid":
            issues.append(line)
        elif st == "statusError":
            errored.append(line)
    if issues:
        return ValidatorResult("kubeconform", "fail", issues)
    if errored:
        return ValidatorResult("kubeconform", "error", detail="; ".join(errored)[:300])
    return ValidatorResult("kubeconform", "pass", detail=json.dumps(data.get("summary", {})))


def run_kube_linter(path: Path, timeout: int = 60) -> ValidatorResult:
    exe = _find("kube-linter")
    if not exe:
        return ValidatorResult("kube-linter", "not_installed")
    cmd = [exe, "lint", "--do-not-auto-add-defaults", "--format", "json"]
    for c in KUBE_LINTER_CHECKS:
        cmd += ["--include", c]
    try:
        p = subprocess.run(cmd + [str(path)], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return ValidatorResult("kube-linter", "error", detail="timeout")
    try:
        data = json.loads(p.stdout or "{}")
    except json.JSONDecodeError:
        return ValidatorResult("kube-linter", "error", detail=(p.stderr or p.stdout)[:300])
    issues = []
    for rep in data.get("Reports") or []:
        obj = rep.get("Object", {}).get("K8sObject", {})
        issues.append(f"{rep.get('Check')}: {obj.get('GroupVersionKind', {}).get('Kind')}/{obj.get('Name')}: "
                      f"{rep.get('Diagnostic', {}).get('Message', '')}")
    if issues:
        return ValidatorResult("kube-linter", "fail", issues)
    if p.returncode != 0:
        return ValidatorResult("kube-linter", "error", detail=p.stderr[:300])
    return ValidatorResult("kube-linter", "pass")


def run_all(path: Path) -> list[ValidatorResult]:
    if os.environ.get("BLASTGUARD_DISABLE_EXTERNAL") == "1":
        return []
    return [run_kubeconform(path), run_kube_linter(path)]
