"""Intent Preservation Gate.

A patch can pass every security check and still change what the workload does: a hostPath that was the whole
point of a log collector becomes an emptyDir, a LoadBalancer Service stops being reachable. This module compares
the original and the accepted patch *structurally* and lists such changes ("drifts").

It is static and conservative: it cannot prove that an app still works in a cluster. A "high" drift means a human
must review before the patch is proposed. No high drift means only "no high-impact static drift detected".
"""
from __future__ import annotations

from typing import Any

from .manifest import containers, pod_spec, ref

HIGH, MEDIUM, INFO = "high", "medium", "info"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
NO_HIGH_IMPACT_DRIFT = "NO_HIGH_IMPACT_DRIFT"
EXPOSING_SERVICE_TYPES = {"LoadBalancer", "NodePort"}
WRITABLE_SOURCES = {"emptyDir", "persistentVolumeClaim", "ephemeral", "nfs", "hostPath"}
# Volume sources whose content outlives the Pod or comes from outside it (red-team addition).
PERSISTENT_SOURCES = {"persistentVolumeClaim", "nfs", "csi", "iscsi", "cephfs", "rbd", "glusterfs", "fc",
                      "azureFile", "azureDisk", "awsElasticBlockStore", "gcePersistentDisk"}
CONFIG_SOURCES = {"configMap", "secret", "projected"}


def _drift(code: str, severity: str, obj: str, detail: str) -> dict:
    return {"code": code, "severity": severity, "object": obj, "detail": detail}


def _dicts(items: Any) -> list[dict]:
    return [i for i in (items or []) if isinstance(i, dict)] if isinstance(items, list) else []


def _volumes(ps: dict) -> dict[str, dict]:
    return {str(v.get("name")): v for v in _dicts(ps.get("volumes"))}


def _source(vol: dict) -> str:
    return next((k for k in vol if k != "name"), "unknown")


def _mounts(c: dict) -> dict[str, dict]:
    return {str(m.get("mountPath")): m for m in _dicts(c.get("volumeMounts"))}


def _tag(image: Any) -> str:
    if not isinstance(image, str) or "@" in image:
        return "digest" if isinstance(image, str) else ""
    last = image.rsplit("/", 1)[-1]
    return last.split(":", 1)[1] if ":" in last else "latest"


def _sc(c: dict) -> dict:
    sc = c.get("securityContext")
    return sc if isinstance(sc, dict) else {}


def _pod_drifts(obj: str, o: dict, n: dict) -> list[dict]:
    out: list[dict] = []
    ov, nv = _volumes(o), _volumes(n)
    for name, vol in ov.items():
        if "hostPath" not in vol:
            continue
        path = (vol.get("hostPath") or {}).get("path") if isinstance(vol.get("hostPath"), dict) else None
        new = nv.get(name)
        if new is None:
            out.append(_drift("HOSTPATH_REMOVED", HIGH, obj,
                              f"hostPath volume '{name}' ({path}) was removed: the workload loses access to host data"))
        elif "hostPath" not in new:
            out.append(_drift("HOSTPATH_REPLACED", HIGH, obj,
                              f"hostPath volume '{name}' ({path}) was replaced by {_source(new)}: the workload no "
                              "longer sees the host files it was mounted to read or write"))
        else:
            npath = (new.get("hostPath") or {}).get("path") if isinstance(new.get("hostPath"), dict) else None
            if npath != path:
                out.append(_drift("HOSTPATH_CHANGED", HIGH, obj, f"hostPath '{name}' path changed {path} -> {npath}"))
    for name, vol in ov.items():
        src = _source(vol)
        kind = "PERSISTENT" if src in PERSISTENT_SOURCES else "CONFIG" if src in CONFIG_SOURCES else None
        if kind is None:
            continue
        new = nv.get(name)
        if new is None:
            out.append(_drift("VOLUME_REMOVED", HIGH, obj,
                              f"{src} volume '{name}' was removed: its data/config is no longer available"))
        elif _source(new) != src:
            out.append(_drift(f"{kind}_VOLUME_REPLACED", HIGH, obj,
                              f"{src} volume '{name}' was replaced by {_source(new)}: "
                              + ("data no longer survives Pod restarts" if kind == "PERSISTENT"
                                 else "the workload no longer receives that config/secret content")))
        elif kind == "PERSISTENT" and new.get(src) != vol.get(src):
            out.append(_drift("PERSISTENT_VOLUME_CHANGED", HIGH, obj,
                              f"{src} volume '{name}' now points at a different backing store"))
    if o.get("hostNetwork") is True and n.get("hostNetwork") is not True:
        out.append(_drift("HOSTNETWORK_REMOVED", HIGH, obj,
                          "hostNetwork was turned off: node IP and host ports are no longer used by the workload"))
    for key in ("hostPID", "hostIPC"):
        if o.get(key) is True and n.get(key) is not True:
            out.append(_drift(f"{key.upper()}_REMOVED", MEDIUM, obj,
                              f"{key} was turned off: the workload no longer sees host processes/IPC"))
    for key in ("serviceAccountName", "nodeSelector", "tolerations", "affinity", "nodeName", "priorityClassName"):
        if o.get(key) != n.get(key) and o.get(key) is not None:
            out.append(_drift(f"{key.upper()}_CHANGED", HIGH, obj, f"{key} changed or was removed (scheduling/identity)"))
    if o.get("automountServiceAccountToken") is not False and n.get("automountServiceAccountToken") is False:
        out.append(_drift("SA_TOKEN_DISABLED", MEDIUM, obj,
                          "service account token is no longer mounted: breaks the app if it calls the Kubernetes API"))
    return out


def _container_drifts(obj: str, wl: dict, oc: dict, nc: dict, n_ps: dict) -> list[dict]:
    out: list[dict] = []
    name = f"{obj} container '{oc.get('name')}'"
    for key in ("command", "args", "env", "envFrom", "livenessProbe", "readinessProbe", "startupProbe", "lifecycle"):
        if oc.get(key) != nc.get(key) and oc.get(key) is not None:
            out.append(_drift(f"{key.upper()}_CHANGED", HIGH, name, f"{key} changed or was removed"))
    o_ports = {(p.get("containerPort"), p.get("protocol", "TCP")) for p in _dicts(oc.get("ports"))}
    n_ports = {(p.get("containerPort"), p.get("protocol", "TCP")) for p in _dicts(nc.get("ports"))}
    if o_ports - n_ports:
        out.append(_drift("PORTS_REMOVED", HIGH, name, f"container ports removed: {sorted(map(str, o_ports - n_ports))}"))
    o_m, n_m = _mounts(oc), _mounts(nc)
    for path in o_m.keys() - n_m.keys():
        out.append(_drift("MOUNT_REMOVED", HIGH, name, f"volume mount at {path} was removed"))
    for path, m in o_m.items():
        if path in n_m and n_m[path].get("readOnly") is True and m.get("readOnly") is not True:
            out.append(_drift("MOUNT_READONLY", MEDIUM, name, f"mount {path} became read-only: writes will fail"))
    o_img, n_img = oc.get("image"), nc.get("image")
    if o_img != n_img:
        ot, nt = _tag(o_img), _tag(n_img)
        out.append(_drift("IMAGE_TAG_CHANGED", MEDIUM, name,
                          f"image tag changed {ot} -> {nt}: behaviour depends on what that tag contains"))
    o_sc, n_sc = _sc(oc), _sc(nc)
    if o_sc.get("privileged") is True and n_sc.get("privileged") is not True:
        out.append(_drift("PRIVILEGED_REMOVED", HIGH, name,
                          "privileged mode was removed: anything needing device or kernel access will fail"))
    o_caps = set((o_sc.get("capabilities") or {}).get("add") or []) if isinstance(o_sc.get("capabilities"), dict) else set()
    n_caps = set((n_sc.get("capabilities") or {}).get("add") or []) if isinstance(n_sc.get("capabilities"), dict) else set()
    if o_caps - n_caps:
        out.append(_drift("CAPABILITIES_REMOVED", MEDIUM, name, f"capabilities no longer added: {sorted(o_caps - n_caps)}"))
    if o_sc.get("runAsUser") not in (None, n_sc.get("runAsUser")) or (
            o_sc.get("runAsNonRoot") is not True and n_sc.get("runAsNonRoot") is True):
        out.append(_drift("USER_CHANGED", MEDIUM, name,
                          f"now runs as non-root (runAsUser {n_sc.get('runAsUser')}): the image must support that user"))
    if o_sc.get("readOnlyRootFilesystem") is not True and n_sc.get("readOnlyRootFilesystem") is True:
        n_vols = _volumes(n_ps)
        writable = any(_source(n_vols.get(str(m.get("name")), {})) in WRITABLE_SOURCES and m.get("readOnly") is not True
                       for m in _dicts(nc.get("volumeMounts")))
        if not writable:
            out.append(_drift("ROOTFS_READONLY_NO_WRITABLE_PATH", HIGH, name,
                              "root filesystem is read-only and no writable volume is mounted: apps that write "
                              "temp/log/cache files will crash"))
    if not (oc.get("resources") or {}).get("limits") and (nc.get("resources") or {}).get("limits"):
        out.append(_drift("LIMITS_ADDED", INFO, name,
                          "resource limits added: too-low values cause OOMKills or CPU throttling"))
    return out


def _service_drifts(obj: str, o: dict, n: dict) -> list[dict]:
    out: list[dict] = []
    os_, ns = o.get("spec") or {}, n.get("spec") or {}
    os_, ns = os_ if isinstance(os_, dict) else {}, ns if isinstance(ns, dict) else {}
    ot, nt = os_.get("type", "ClusterIP"), ns.get("type", "ClusterIP")
    if ot in EXPOSING_SERVICE_TYPES and nt != ot:
        out.append(_drift("SERVICE_EXPOSURE_CHANGED", HIGH, obj,
                          f"Service type {ot} -> {nt}: clients outside the cluster can no longer reach it"))
    if os_.get("selector") != ns.get("selector"):
        out.append(_drift("SERVICE_SELECTOR_CHANGED", HIGH, obj, "Service selector changed: traffic goes elsewhere"))
    op = {(p.get("port"), p.get("targetPort"), p.get("protocol", "TCP")) for p in _dicts(os_.get("ports"))}
    np_ = {(p.get("port"), p.get("targetPort"), p.get("protocol", "TCP")) for p in _dicts(ns.get("ports"))}
    if op - np_:
        out.append(_drift("SERVICE_PORTS_CHANGED", HIGH, obj, f"Service ports changed or removed: {sorted(map(str, op - np_))}"))
    return out


def intent_drifts(original: list[dict], patched: list[dict]) -> list[dict]:
    """Structural differences between original and patched manifests that change what the app does."""
    new = {ref(d): d for d in patched}
    out: list[dict] = []
    for d in original:
        r = ref(d)
        nd = new.get(r)
        if nd is None:
            continue  # removal is the identity guard's job
        obj = str(r)
        if d.get("kind") == "Service":
            out += _service_drifts(obj, d, nd)
            continue
        ops, nps = pod_spec(d), pod_spec(nd)
        if ops is None or nps is None:
            continue
        o_rep, n_rep = (d.get("spec") or {}).get("replicas"), (nd.get("spec") or {}).get("replicas")
        if o_rep != n_rep and o_rep is not None:
            out.append(_drift("REPLICAS_CHANGED", HIGH, obj, f"replicas {o_rep} -> {n_rep}"))
        out += _pod_drifts(obj, ops, nps)
        n_by_name = {str(c.get("name")): c for c in containers(nps)}
        for oc in containers(ops):
            nc = n_by_name.get(str(oc.get("name")))
            if nc is not None:
                out += _container_drifts(obj, d, oc, nc, nps)
    return out


def intent_report(original: list[dict], patched: list[dict]) -> dict:
    """Verdict + drifts. Fails closed: if the gate itself errors, a human review is required."""
    try:
        drifts = intent_drifts(original, patched)
    except Exception as exc:  # fail closed on any malformed structure
        return {"verdict": REVIEW_REQUIRED, "drifts": [],
                "error": f"intent gate error: {exc.__class__.__name__}",
                "note": "The gate could not analyse this patch, so review is required."}
    high = [x for x in drifts if x["severity"] == HIGH]
    return {"verdict": REVIEW_REQUIRED if high else NO_HIGH_IMPACT_DRIFT, "drifts": drifts, "error": None,
            "note": ("A security-clean patch changed what the workload does. Review before proposing."
                     if high else "No high-impact static drift detected. Behaviour in a cluster is still not proven.")}
