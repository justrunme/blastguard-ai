"""Remediation loop: detect -> propose (LLM) -> sandbox -> verify independently -> retry."""
from __future__ import annotations

import difflib
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from . import validators
from .checks import blocking, run_checks
from .guard import identity_violations
from .intent import REVIEW_REQUIRED, intent_report
from .llm import LLMError, Proposal
from .manifest import ManifestError, parse_manifest

MAX_ATTEMPTS = 3
MAX_WALL_S = 300.0

BLOCKED, VERIFIED, UNRESOLVED = "BLOCKED", "VERIFIED", "UNRESOLVED"


class PatchClient(Protocol):
    model: str

    def propose(self, manifest: str, findings: list[dict], feedback: list[str]) -> Proposal: ...


@dataclass
class RunResult:
    status: str
    initial_status: str
    original_yaml: str
    final_yaml: str | None
    initial_findings: list[dict]
    attempts: list[dict] = field(default_factory=list)
    error: str | None = None
    model: str | None = None
    validators_initial: list[dict] = field(default_factory=list)
    wall_s: float = 0.0
    events: list[str] = field(default_factory=list)
    last_candidate: str | None = None
    intent: dict | None = None

    @property
    def diff(self) -> str:
        if not self.final_yaml:
            return ""
        return "".join(difflib.unified_diff(self.original_yaml.splitlines(True), self.final_yaml.splitlines(True),
                                            "original.yaml", "patched.yaml"))

    @property
    def release(self) -> str:
        """Final decision: security status AND intent preservation."""
        if self.status != VERIFIED:
            return "NOT_PROPOSED" if self.status == UNRESOLVED else "BLOCKED"
        if self.intent and self.intent["verdict"] == REVIEW_REQUIRED:
            return "REVIEW_REQUIRED"
        return "SAFE_TO_PROPOSE"

    def totals(self) -> dict:
        t = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "llm_latency_s": 0.0}
        for a in self.attempts:
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                t[k] += int((a.get("usage") or {}).get(k) or 0)
            t["llm_latency_s"] += a.get("llm_latency_s") or 0.0
        t["llm_latency_s"] = round(t["llm_latency_s"], 2)
        return t


def verify(original_docs: list[dict], patched_text: str, sandbox: Path, attempt: int) -> dict:
    """Independent verification of a candidate manifest. Returns a dict with ok + evidence."""
    out: dict = {"ok": False, "findings": [], "guard": [], "validators": [], "parse_error": None}
    try:
        docs = parse_manifest(patched_text)
    except ManifestError as exc:
        out["parse_error"] = str(exc)
        return out
    path = sandbox / f"attempt-{attempt}.yaml"
    path.write_text(patched_text, encoding="utf-8")
    out["findings"] = [f.to_dict() for f in run_checks(docs)]
    out["guard"] = identity_violations(original_docs, docs)
    out["validators"] = [v.to_dict() for v in validators.run_all(path)]
    out["ok"] = (not out["guard"] and not [f for f in out["findings"] if f["blocking"]]
                 and not any(v["status"] == "fail" for v in out["validators"]))
    return out


def _feedback(v: dict) -> list[str]:
    fb = []
    if v["parse_error"]:
        fb.append(f"Output was rejected: {v['parse_error']}")
    fb += [f"Identity guard: {g}" for g in v["guard"]]
    fb += [f"Still failing {f['rule_id']} on {f['object']} container={f['container']}: {f['message']}"
           for f in v["findings"] if f["blocking"]]
    for val in v["validators"]:
        if val["status"] == "fail":
            fb += [f"{val['name']}: {i}" for i in val["issues"][:10]]
    return fb or ["Previous output was not usable"]


def run_remediation(manifest_text, client: PatchClient | None, max_attempts: int = MAX_ATTEMPTS,
                    max_wall_s: float = MAX_WALL_S, on_event: Callable[[str], None] | None = None) -> RunResult:
    t0 = time.monotonic()
    max_attempts = max(0, min(int(max_attempts), MAX_ATTEMPTS))
    events: list[str] = []

    def log(msg: str) -> None:
        events.append(f"[{time.monotonic() - t0:6.1f}s] {msg}")
        if on_event:
            on_event(msg)

    original = manifest_text if isinstance(manifest_text, str) else ""
    try:
        docs = parse_manifest(manifest_text)
    except ManifestError as exc:
        log(f"Input rejected: {exc}")
        return RunResult(UNRESOLVED, UNRESOLVED, original, None, [], error=f"input rejected: {exc}",
                         wall_s=time.monotonic() - t0, events=events)

    findings = [f.to_dict() for f in run_checks(docs)]
    block = [f for f in findings if f["blocking"]]
    with tempfile.TemporaryDirectory(prefix="blastguard-sandbox-") as tmp:
        sandbox = Path(tmp)
        (sandbox / "original.yaml").write_text(original, encoding="utf-8")
        val0 = [v.to_dict() for v in validators.run_all(sandbox / "original.yaml")]
        log(f"Deterministic checks: {len(findings)} findings ({len(block)} blocking)")
        for v in val0:
            log(f"Validator {v['name']}: {v['status']}")
        initial = BLOCKED if block or any(v["status"] == "fail" for v in val0) else VERIFIED
        res = RunResult(initial, initial, original, None, findings, model=getattr(client, "model", None),
                        validators_initial=val0, events=events)
        if initial == VERIFIED:
            log("No blocking findings: nothing to remediate")
            res.final_yaml = original
        elif client is None or max_attempts == 0:
            log("Remediation not run (no LLM client): status stays BLOCKED")
        else:
            current, feedback = original, []
            current_findings = block
            res.status = UNRESOLVED
            for n in range(1, max_attempts + 1):
                if time.monotonic() - t0 > max_wall_s:
                    log("Wall-time budget exhausted")
                    res.error = "wall-time budget exhausted"
                    break
                log(f"Attempt {n}/{max_attempts}: asking {getattr(client, 'model', 'model')} for a patch")
                att: dict = {"attempt": n, "feedback_given": feedback}
                try:
                    p = client.propose(current, current_findings, feedback)
                except LLMError as exc:
                    att["error"] = str(exc)
                    res.attempts.append(att)
                    res.error = f"LLM API error: {exc}"
                    log(f"LLM API error, stopping: {exc}")
                    break
                att.update({"llm_latency_s": round(p.latency_s, 2), "usage": p.usage, "channel": p.channel,
                            "rationale": p.rationale, "proposed_yaml": p.patched_yaml})
                if not p.patched_yaml or not isinstance(p.patched_yaml, str):
                    v = {"ok": False, "findings": [], "guard": [], "validators": [],
                         "parse_error": "model returned no YAML"}
                else:
                    v = verify(docs, p.patched_yaml, sandbox, n)
                att["verification"] = v
                res.attempts.append(att)
                nb = len([f for f in v["findings"] if f["blocking"]])
                log(f"Attempt {n} verification: {'PASS' if v['ok'] else 'FAIL'} "
                    f"(blocking={nb}, guard={len(v['guard'])}, parse_error={v['parse_error']})")
                if v["ok"]:
                    res.status, res.final_yaml = VERIFIED, p.patched_yaml
                    res.intent = intent_report(docs, parse_manifest(p.patched_yaml))
                    log(f"Intent gate: {res.intent['verdict']} ({len(res.intent['drifts'])} drifts)")
                    break
                feedback = _feedback(v)
                if not v["parse_error"] and not v["guard"]:
                    current = p.patched_yaml
                    current_findings = [f for f in v["findings"] if f["blocking"]] or current_findings
                if not v["parse_error"]:
                    res.last_candidate = p.patched_yaml  # shown only as an UNVERIFIED candidate
            log(f"Final status: {res.status}")
    res.wall_s = round(time.monotonic() - t0, 2)
    return res
