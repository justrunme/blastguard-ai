"""Deterministic security rules. Independent of any LLM."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .manifest import containers, pod_spec, ref, WORKLOAD_KINDS

DANGEROUS_CAPS = {"ALL", "SYS_ADMIN", "NET_ADMIN", "SYS_PTRACE", "SYS_MODULE"}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str  # critical | high | medium | info
    object: str
    container: str
    message: str

    @property
    def blocking(self) -> bool:
        return self.severity != "info"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["blocking"] = self.blocking
        return d


RULES = {
    "BG001": ("critical", "Privileged container"),
    "BG002": ("critical", "hostPath volume mounted"),
    "BG003": ("high", "hostNetwork enabled"),
    "BG004": ("high", "hostPID / hostIPC enabled"),
    "BG005": ("high", "May run as root (runAsNonRoot not true or runAsUser 0)"),
    "BG006": ("high", "allowPrivilegeEscalation not explicitly false"),
    "BG007": ("medium", "Missing CPU/memory limits"),
    "BG008": ("medium", "Image uses :latest or has no tag/digest"),
    "BG009": ("medium", "readOnlyRootFilesystem not true"),
    "BG010": ("critical", "Dangerous Linux capability added"),
    "BG011": ("medium", "Service account token automounted"),
    "BG012": ("high", "Service exposed via LoadBalancer"),
    "BG013": ("info", "No NetworkPolicy in this manifest bundle"),
}


def _f(rule: str, obj, container: str, detail: str = "") -> Finding:
    sev, title = RULES[rule]
    return Finding(rule, sev, str(obj), container, title + (f": {detail}" if detail else ""))


def _image_unpinned(image: str) -> bool:
    if "@sha256:" in image:
        return False
    last = image.rsplit("/", 1)[-1]
    if ":" not in last:
        return True
    return last.rsplit(":", 1)[1] in ("", "latest")


def _sc(obj) -> dict:
    return obj if isinstance(obj, dict) else {}


def check_workload(doc: dict) -> list[Finding]:
    ps = pod_spec(doc)
    if ps is None:
        return []
    r = ref(doc)
    out: list[Finding] = []
    pod_sc = _sc(ps.get("securityContext"))

    for v in ps.get("volumes") or []:
        if isinstance(v, dict) and "hostPath" in v:
            path = _sc(v.get("hostPath")).get("path", "?")
            out.append(_f("BG002", r, "-", f"volume '{v.get('name')}' -> {path}"))
    if ps.get("hostNetwork") is True:
        out.append(_f("BG003", r, "-"))
    if ps.get("hostPID") is True or ps.get("hostIPC") is True:
        out.append(_f("BG004", r, "-"))
    if ps.get("automountServiceAccountToken") is not False:
        out.append(_f("BG011", r, "-", "set automountServiceAccountToken: false unless the API is needed"))

    for c in containers(ps):
        name = str(c.get("name", "?"))
        sc = _sc(c.get("securityContext"))
        if sc.get("privileged") is True:
            out.append(_f("BG001", r, name))
        non_root = sc.get("runAsNonRoot", pod_sc.get("runAsNonRoot"))
        run_as_user = sc.get("runAsUser", pod_sc.get("runAsUser"))
        if non_root is not True or run_as_user == 0:
            out.append(_f("BG005", r, name))
        if sc.get("allowPrivilegeEscalation") is not False:
            out.append(_f("BG006", r, name))
        limits = _sc(_sc(c.get("resources")).get("limits"))
        missing = [k for k in ("cpu", "memory") if k not in limits]
        if missing:
            out.append(_f("BG007", r, name, "missing " + ",".join(missing)))
        image = c.get("image")
        if not isinstance(image, str) or _image_unpinned(image):
            out.append(_f("BG008", r, name, str(image)))
        if sc.get("readOnlyRootFilesystem") is not True:
            out.append(_f("BG009", r, name))
        added = {str(x).upper() for x in (_sc(sc.get("capabilities")).get("add") or [])}
        bad = sorted(added & DANGEROUS_CAPS)
        if bad:
            out.append(_f("BG010", r, name, ",".join(bad)))
    return out


def check_service(doc: dict) -> list[Finding]:
    if doc.get("kind") != "Service":
        return []
    if _sc(doc.get("spec")).get("type") == "LoadBalancer":
        return [_f("BG012", ref(doc), "-", "use ClusterIP behind an Ingress/gateway")]
    return []


def run_checks(docs: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    for d in docs:
        findings += check_workload(d)
        findings += check_service(d)
    has_workload = any(d.get("kind") in WORKLOAD_KINDS for d in docs)
    has_netpol = any(d.get("kind") == "NetworkPolicy" for d in docs)
    if has_workload and not has_netpol:
        findings.append(_f("BG013", "bundle", "-", "consider a default-deny NetworkPolicy"))
    return findings


def blocking(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.blocking]
