"""Fail-closed parsing of Kubernetes manifest YAML."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

MAX_MANIFEST_BYTES = 64 * 1024
MAX_DOCUMENTS = 20

WORKLOAD_KINDS = {"Pod", "Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob"}


class ManifestError(ValueError):
    """Raised when input cannot be safely analysed. Callers must treat it as a failure."""


@dataclass(frozen=True)
class ObjRef:
    kind: str
    name: str
    namespace: str

    def __str__(self) -> str:
        return f"{self.kind}/{self.namespace}/{self.name}"


def parse_manifest(text: Any) -> list[dict]:
    if not isinstance(text, str):
        raise ManifestError("manifest must be text")
    if len(text.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ManifestError(f"manifest exceeds {MAX_MANIFEST_BYTES} bytes")
    if not text.strip():
        raise ManifestError("manifest is empty")
    try:
        docs = [d for d in yaml.safe_load_all(text) if d is not None]
    except yaml.YAMLError as exc:
        raise ManifestError(f"invalid YAML: {exc.__class__.__name__}") from exc
    if not docs:
        raise ManifestError("manifest contains no documents")
    if len(docs) > MAX_DOCUMENTS:
        raise ManifestError(f"too many documents (> {MAX_DOCUMENTS})")
    for i, d in enumerate(docs):
        if not isinstance(d, dict):
            raise ManifestError(f"document {i} is not a mapping")
        if not isinstance(d.get("kind"), str) or not isinstance(d.get("apiVersion"), str):
            raise ManifestError(f"document {i} lacks apiVersion/kind")
        meta = d.get("metadata")
        if not isinstance(meta, dict) or not isinstance(meta.get("name"), str):
            raise ManifestError(f"document {i} lacks metadata.name")
    return docs


def ref(doc: dict) -> ObjRef:
    meta = doc.get("metadata") or {}
    return ObjRef(doc["kind"], meta["name"], str(meta.get("namespace") or "default"))


def pod_spec(doc: dict) -> dict | None:
    """Return the pod spec of a workload, or None if not a workload / malformed."""
    kind = doc.get("kind")
    spec = doc.get("spec")
    if kind not in WORKLOAD_KINDS or not isinstance(spec, dict):
        return None
    try:
        if kind == "Pod":
            ps = spec
        elif kind == "CronJob":
            ps = spec["jobTemplate"]["spec"]["template"]["spec"]
        else:
            ps = spec["template"]["spec"]
    except (KeyError, TypeError):
        return None
    return ps if isinstance(ps, dict) else None


def containers(ps: dict) -> list[dict]:
    out = []
    for key in ("initContainers", "containers"):
        for c in ps.get(key) or []:
            if isinstance(c, dict):
                out.append(c)
    return out
