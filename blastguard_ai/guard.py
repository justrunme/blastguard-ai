"""Identity guard: the patch must fix the workload, not delete or swap it."""
from __future__ import annotations

from .manifest import containers, pod_spec, ref

ALLOWED_NEW_KINDS = {"NetworkPolicy", "ServiceAccount"}


def image_repo(image) -> str:
    if not isinstance(image, str):
        return ""
    image = image.split("@", 1)[0]
    head, _, last = image.rpartition("/")
    last = last.split(":", 1)[0]
    return f"{head}/{last}" if head else last


def _shape(doc: dict) -> dict:
    ps = pod_spec(doc)
    if ps is None:
        return {}
    return {str(c.get("name")): image_repo(c.get("image")) for c in containers(ps)}


def identity_violations(original: list[dict], patched: list[dict]) -> list[str]:
    errs: list[str] = []
    orig = {ref(d): d for d in original}
    new = {ref(d): d for d in patched}
    for r, od in orig.items():
        nd = new.get(r)
        if nd is None:
            errs.append(f"{r} was removed or renamed")
            continue
        if pod_spec(od) is not None and pod_spec(nd) is None:
            errs.append(f"{r} lost its pod spec")
            continue
        o_shape, n_shape = _shape(od), _shape(nd)
        for cname, repo in o_shape.items():
            if cname not in n_shape:
                errs.append(f"{r}: container '{cname}' was removed")
            elif n_shape[cname] != repo:
                errs.append(f"{r}: container '{cname}' image repo changed {repo} -> {n_shape[cname]}")
        o_rep = (od.get("spec") or {}).get("replicas")
        n_rep = (nd.get("spec") or {}).get("replicas")
        if n_rep == 0 and o_rep != 0:
            errs.append(f"{r}: replicas scaled to 0")
    for r in new:
        if r not in orig and r.kind not in ALLOWED_NEW_KINDS:
            errs.append(f"{r}: unexpected new object of kind {r.kind}")
    return errs
