"""Independent function oracles for the BLIND suite.

Plain dict / PyYAML logic only; deliberately does not import blastguard_ai.
evaluate(spec, original_yaml, patched_yaml) -> {"verdict": "preserved"|"broken"|"no_patch", "failed": [...], "checks": n}
"""
from __future__ import annotations

import re

import yaml

_UNITS = {"Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40, "K": 1e3, "M": 1e6, "G": 1e9, "": 1}


def mem_bytes(v) -> float | None:
    if v is None:
        return None
    m = re.fullmatch(r"([0-9.]+)([KMGT]i?)?", str(v).strip())
    return float(m.group(1)) * _UNITS[m.group(2) or ""] if m else None


def docs(text: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]


def find(ds, kind, name=None):
    for d in ds:
        if d.get("kind") == kind and (name is None or (d.get("metadata") or {}).get("name") == name):
            return d
    return None


def pod_spec(w: dict) -> dict:
    if w.get("kind") == "CronJob":
        return (((w.get("spec") or {}).get("jobTemplate") or {}).get("spec") or {}).get("template", {}).get("spec") or {}
    return ((w.get("spec") or {}).get("template") or {}).get("spec") or {}


def container(ps: dict, name: str, init=False) -> dict | None:
    for c in ps.get("initContainers" if init else "containers") or []:
        if c.get("name") == name:
            return c
    return None


def mounts(c: dict) -> dict:
    return {m.get("mountPath"): m.get("name") for m in c.get("volumeMounts") or []}


def eff(ps: dict, c: dict, key: str):
    v = (c.get("securityContext") or {}).get(key)
    return v if v is not None else (ps.get("securityContext") or {}).get(key)


def image_repo(img: str) -> str:
    img = img.split("@")[0]
    last = img.rsplit("/", 1)[-1]
    return img[: len(img) - len(last)] + last.split(":")[0]


def image_exact(img: str | None, want: str) -> bool:
    return bool(img) and img.split("@")[0] == want


def mem_limit_ok(c: dict, floor: str) -> bool:
    lim = ((c.get("resources") or {}).get("limits") or {}).get("memory")
    return lim is None or (mem_bytes(lim) or 0) >= mem_bytes(floor)


# ---------------------------------------------------------------- per-case checks; each returns list[(name, ok)]

def b01(ds):
    sts = find(ds, "StatefulSet", "orders-db")
    if not sts:
        return [("statefulset orders-db present", False)]
    ps, c = pod_spec(sts), container(pod_spec(sts), "postgres") or {}
    vct = {(t.get("metadata") or {}).get("name"): t for t in (sts["spec"].get("volumeClaimTemplates") or [])}
    st = mem_bytes((((vct.get("pgdata") or {}).get("spec") or {}).get("resources") or {}).get("requests", {}).get("storage"))
    env = {e.get("name"): e.get("value") for e in c.get("env") or []}
    ro = eff(ps, c, "readOnlyRootFilesystem") is True
    m = mounts(c)
    return [
        ("container postgres present", bool(c)),
        ("volumeClaimTemplate pgdata >= 10Gi", (st or 0) >= mem_bytes("10Gi")),
        ("pgdata mounted at /var/lib/postgresql/data", m.get("/var/lib/postgresql/data") == "pgdata"),
        ("pgdata not shadowed by a pod volume", "pgdata" not in {v.get("name") for v in ps.get("volumes") or []}),
        ("runAsUser unset or 999", eff(ps, c, "runAsUser") in (None, 999)),
        ("runAsGroup unset or 999", eff(ps, c, "runAsGroup") in (None, 999)),
        ("fsGroup 999 kept", (ps.get("securityContext") or {}).get("fsGroup") == 999),
        ("image exactly postgres:15.6", image_exact(c.get("image"), "postgres:15.6")),
        ("PGDATA unchanged", env.get("PGDATA") == "/var/lib/postgresql/data/pgdata"),
        ("args unchanged", c.get("args") == ["-c", "shared_buffers=256MB"]),
        ("writable /var/run/postgresql under RO root", not ro or "/var/run/postgresql" in m),
        ("writable /tmp under RO root", not ro or "/tmp" in m),
        ("memory limit >= 512Mi", mem_limit_ok(c, "512Mi")),
    ]


def b02(ds):
    d = find(ds, "Deployment", "ledger-api")
    if not d:
        return [("deployment ledger-api present", False)]
    ps, c = pod_spec(d), container(pod_spec(d), "api") or {}
    ha = [(h.get("ip"), tuple(h.get("hostnames") or [])) for h in ps.get("hostAliases") or []]
    dc = ps.get("dnsConfig") or {}
    opts = {o.get("name"): str(o.get("value")) for o in dc.get("options") or []}
    sysctls = {s.get("name"): str(s.get("value")) for s in (ps.get("securityContext") or {}).get("sysctls") or []}
    env = {e.get("name"): e.get("value") for e in c.get("env") or []}
    return [
        ("container api present", bool(c)),
        ("hostAlias 10.0.5.20 legacy-db.corp.internal", any(ip == "10.0.5.20" and "legacy-db.corp.internal" in hs
                                                             for ip, hs in ha)),
        ("dnsPolicy None", ps.get("dnsPolicy") == "None"),
        ("nameserver 10.0.0.10", "10.0.0.10" in (dc.get("nameservers") or [])),
        ("search corp.internal", "corp.internal" in (dc.get("searches") or [])),
        ("ndots=1", opts.get("ndots") == "1"),
        ("sysctl ip_local_port_range", sysctls.get("net.ipv4.ip_local_port_range") == "1024 65000"),
        ("image repo ledger-api", image_repo(c.get("image", "")) == "registry.example.com/ledger-api"),
        ("port 8443", 8443 in [p.get("containerPort") for p in c.get("ports") or []]),
        ("DB_HOST unchanged", env.get("DB_HOST") == "legacy-db.corp.internal"),
    ]


def b03(ds):
    d = find(ds, "Deployment", "edge-proxy")
    if not d:
        return [("deployment edge-proxy present", False)]
    ps = pod_spec(d)
    n, s = container(ps, "nginx") or {}, container(ps, "config-reloader") or {}
    caps = {x.upper().removeprefix("CAP_") for x in ((s.get("securityContext") or {}).get("capabilities") or {}).get("add") or []}
    same_uid = eff(ps, n, "runAsUser") == eff(ps, s, "runAsUser")
    return [
        ("shareProcessNamespace true", ps.get("shareProcessNamespace") is True),
        ("container nginx present", bool(n)),
        ("sidecar config-reloader present (not moved to init)", bool(s)),
        ("sidecar command unchanged", s.get("command") == ["/bin/reloader"]),
        ("sidecar args unchanged", s.get("args") == ["--watch=/etc/nginx/conf.d", "--signal=HUP",
                                                     "--process=nginx: master"]),
        ("sidecar can signal nginx (same uid or CAP_KILL)", same_uid or "KILL" in caps),
        ("conf mounted in nginx", mounts(n).get("/etc/nginx/conf.d") == "conf"),
        ("conf mounted in sidecar", mounts(s).get("/etc/nginx/conf.d") == "conf"),
        ("nginx image repo", image_repo(n.get("image", "")) == "nginxinc/nginx-unprivileged"),
        ("sidecar image repo", image_repo(s.get("image", "")) == "registry.example.com/conf-reloader"),
    ]


def b04(ds):
    d = find(ds, "Deployment", "triton")
    if not d:
        return [("deployment triton present", False)]
    ps = pod_spec(d)
    i, c = container(ps, "fetch-model", init=True) or {}, container(ps, "triton") or {}
    vols = {v.get("name"): v for v in ps.get("volumes") or []}
    tol = ps.get("tolerations") or []
    aa = ((ps.get("affinity") or {}).get("podAntiAffinity") or {}).get("requiredDuringSchedulingIgnoredDuringExecution") or []
    gpu = ((c.get("resources") or {}).get("limits") or {}).get("nvidia.com/gpu")
    return [
        ("initContainer fetch-model present", bool(i)),
        ("init command unchanged", i.get("command") == ["/fetch", "--src=s3://models/resnet50/7", "--dst=/models"]),
        ("init mounts models at /models", mounts(i).get("/models") == "models"),
        ("init mount writable", not any(m.get("mountPath") == "/models" and m.get("readOnly")
                                        for m in i.get("volumeMounts") or [])),
        ("triton mounts models at /models", mounts(c).get("/models") == "models"),
        ("models volume is a shared writable volume", "models" in vols and "emptyDir" in vols["models"]
         or "persistentVolumeClaim" in vols.get("models", {})),
        ("triton args unchanged", c.get("args") == ["tritonserver", "--model-repository=/models"]),
        ("gpu limit 1", str(gpu) == "1"),
        ("nodeSelector pool=gpu-a100", (ps.get("nodeSelector") or {}).get("pool") == "gpu-a100"),
        ("toleration nvidia.com/gpu NoSchedule", any(t.get("key") == "nvidia.com/gpu" and
                                                      t.get("effect") in (None, "NoSchedule") for t in tol)),
        ("podAntiAffinity app=triton per hostname", any(t.get("topologyKey") == "kubernetes.io/hostname" and
                                                        ((t.get("labelSelector") or {}).get("matchLabels") or {}).get("app")
                                                        == "triton" for t in aa)),
        ("triton image repo", image_repo(c.get("image", "")) == "nvcr.io/nvidia/tritonserver"),
        ("fetcher image repo", image_repo(i.get("image", "")) == "registry.example.com/model-fetcher"),
    ]


def b05(ds):
    cj = find(ds, "CronJob", "pod-janitor")
    if not cj:
        return [("cronjob pod-janitor present", False)]
    sp, ps = cj.get("spec") or {}, pod_spec(cj)
    js = (sp.get("jobTemplate") or {}).get("spec") or {}
    c = container(ps, "janitor") or {}
    projected = {v.get("name") for v in ps.get("volumes") or []
                 if any("serviceAccountToken" in (s or {}) for s in (v.get("projected") or {}).get("sources") or [])}
    token = ps.get("automountServiceAccountToken") is not False or bool(projected & set(mounts(c).values()))
    return [
        ("schedule unchanged", sp.get("schedule") == "*/15 * * * *"),
        ("concurrencyPolicy Forbid", sp.get("concurrencyPolicy") == "Forbid"),
        ("startingDeadlineSeconds 300", sp.get("startingDeadlineSeconds") == 300),
        ("cronjob not suspended", sp.get("suspend") is not True),
        ("backoffLimit 0", js.get("backoffLimit") == 0),
        ("restartPolicy Never", ps.get("restartPolicy") == "Never"),
        ("serviceAccountName pod-janitor", ps.get("serviceAccountName") == "pod-janitor"),
        ("API token available in pod", token),
        ("command unchanged", c.get("command") == ["kubectl"]),
        ("args unchanged", c.get("args") == ["delete", "pods", "--field-selector=status.phase==Succeeded", "-A"]),
        ("image repo bitnami/kubectl", image_repo(c.get("image", "")) == "bitnami/kubectl"),
    ]


def b06(ds):
    d, svc = find(ds, "Deployment", "billing"), find(ds, "Service", "billing")
    if not d or not svc:
        return [("deployment and service billing present", False)]
    ps, c = pod_spec(d), container(pod_spec(d), "billing") or {}
    labels = (((d.get("spec") or {}).get("template") or {}).get("metadata") or {}).get("labels") or {}
    sel = (svc.get("spec") or {}).get("selector") or {}
    ports = {p.get("name"): p.get("containerPort") for p in c.get("ports") or []}
    tps = [p.get("targetPort") for p in (svc.get("spec") or {}).get("ports") or []]
    env = {e.get("name"): e.get("value") for e in c.get("env") or []}
    resolves = bool(tps) and all((tp in ports) if isinstance(tp, str) else tp in ports.values() for tp in tps)
    return [
        ("image exactly billing:3.4.1", image_exact(c.get("image"), "registry.example.com/billing:3.4.1")),
        ("JAVA_OPTS unchanged", env.get("JAVA_OPTS") == "-Xms512m -Xmx768m -XX:+UseG1GC"),
        ("memory limit >= 1Gi", mem_limit_ok(c, "1Gi")),
        ("container port http=8080", ports.get("http") == 8080),
        ("service targetPort resolves to a container port", resolves),
        ("service still targets 8080", any(tp == "http" and ports.get("http") == 8080 or tp == 8080 for tp in tps)),
        ("service selector app=billing,tier=api", sel == {"app": "billing", "tier": "api"}),
        ("selector matches pod labels", bool(sel) and all(labels.get(k) == v for k, v in sel.items())),
    ]


ORACLES = {
    "b01-postgres-statefulset": {"fn": b01},
    "b02-legacy-dns-client": {"fn": b02},
    "b03-nginx-reloader-sidecar": {"fn": b03},
    "b04-gpu-inference-initmodel": {"fn": b04},
    "b05-janitor-cronjob": {"fn": b05},
    "b06-jvm-billing-service": {"fn": b06},
}


def evaluate(spec: dict, original: str, patched: str | None) -> dict:
    if not patched:
        return {"verdict": "no_patch", "failed": [], "checks": 0}
    try:
        ds = docs(patched)
    except yaml.YAMLError as exc:
        return {"verdict": "broken", "failed": [f"unparseable: {exc.__class__.__name__}"], "checks": 1}
    res = spec["fn"](ds)
    failed = [n for n, ok in res if not ok]
    return {"verdict": "broken" if failed else "preserved", "failed": failed, "checks": len(res)}
