"""Evidence report (JSON + Markdown)."""
from __future__ import annotations

import datetime as dt
import json

from . import __version__
from .loop import RunResult


def to_dict(res: RunResult, source: str = "") -> dict:
    return {
        "tool": "blastguard-ai", "version": __version__,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": source, "model": res.model,
        "initial_status": res.initial_status, "final_status": res.status, "error": res.error,
        "initial_findings": res.initial_findings, "validators_initial": res.validators_initial,
        "attempts": res.attempts, "totals": res.totals(), "wall_s": res.wall_s,
        "release": res.release, "release_note": res.release_note, "validators_complete": res.validators_complete, "intent": res.intent, "diff": res.diff, "final_yaml": res.final_yaml, "last_unverified_candidate": res.last_candidate,
        "events": res.events,
    }


def to_json(res: RunResult, source: str = "") -> str:
    return json.dumps(to_dict(res, source), indent=2, default=str)


def to_markdown(res: RunResult, source: str = "") -> str:
    d = to_dict(res, source)
    t = d["totals"]
    lines = [f"# BlastGuard AI evidence report", "",
             f"- Source: `{source or 'input'}`", f"- Model: `{res.model}`",
             f"- Status: **{res.initial_status} -> {res.status}**",
             f"- Attempts: {len(res.attempts)}  |  Wall time: {res.wall_s}s  |  "
             f"Tokens: {t['total_tokens']} (prompt {t['prompt_tokens']}, completion {t['completion_tokens']})"]
    lines.append(f"- Release decision: **{res.release}**")
    if res.release_note:
        lines.append(f"- Note: {res.release_note}")
    if res.error:
        lines.append(f"- Error: {res.error}")
    lines += ["", "## Initial findings", "", "| Rule | Severity | Object | Container | Message |", "|---|---|---|---|---|"]
    lines += [f"| {f['rule_id']} | {f['severity']} | {f['object']} | {f['container']} | {f['message']} |"
              for f in res.initial_findings]
    lines += ["", "Initial validators: " + (", ".join(f"{v['name']}={v['status']}" for v in res.validators_initial)
                                            or "none")]
    for a in res.attempts:
        lines += ["", f"## Attempt {a['attempt']}"]
        if a.get("error"):
            lines.append(f"- API error: {a['error']}")
            continue
        v = a.get("verification", {})
        u = a.get("usage") or {}
        lines += [f"- Channel: {a.get('channel')}  |  LLM latency: {a.get('llm_latency_s')}s  |  "
                  f"tokens: {u.get('total_tokens')}",
                  f"- Verification: {'PASS' if v.get('ok') else 'FAIL'}"]
        if v.get("parse_error"):
            lines.append(f"- Parse error: {v['parse_error']}")
        for g in v.get("guard", []):
            lines.append(f"- Guard: {g}")
        rem = [f for f in v.get("findings", []) if f["blocking"]]
        lines.append(f"- Remaining blocking findings: {len(rem)}")
        lines += [f"  - {f['rule_id']} {f['object']} {f['container']}: {f['message']}" for f in rem]
        for val in v.get("validators", []):
            lines.append(f"- {val['name']}: {val['status']}" + (f" ({len(val['issues'])} issues)" if val['issues'] else ""))
        if a.get("rationale"):
            lines += ["- Model rationale:", "", "> " + a["rationale"].replace("\n", "\n> ")]
    if res.intent:
        lines += ["", "## Intent Preservation Gate", "", f"Verdict: **{res.intent['verdict']}**. {res.intent['note']}"]
        if res.intent["drifts"]:
            lines += ["", "| Severity | Code | Object | What changed |", "|---|---|---|---|"]
            lines += [f"| {x['severity']} | {x['code']} | {x['object']} | {x['detail']} |"
                      for x in res.intent["drifts"]]
    if res.diff:
        lines += ["", "## Verified diff", "", "```diff", res.diff.rstrip(), "```"]
    return "\n".join(lines) + "\n"
