"""Run the BlastGuard benchmark corpus through the real Nemotron loop and score it with independent oracles.

Usage:
  .venv/bin/python scripts/run_benchmark.py [--repeats 3] [--cases 01,03] [--only-failed]
  .venv/bin/python scripts/run_benchmark.py --offline      # rebuild results from saved raw JSON, no API calls
  .venv/bin/python scripts/run_benchmark.py --suite blind  # blind corpus in benchmark/blind/ (own oracles, own results/)
Requires NEBIUS_API_KEY for online mode (read from the environment; never printed).
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark.oracles import ORACLES, evaluate  # noqa: E402

BENCH = ROOT / "benchmark"
RAW = BENCH / "results" / "raw"
MAX_TOTAL_RUNS = 150
PER_RUN_WALL_S = 120.0
CORPUS_NOTE = ("- All statements below hold **on this corpus** only (16 hand-written cases). It is small and authored by the "
               "same project; it is not evidence about Kubernetes manifests in general.")
MATRIX = ("TRUE_REVIEW", "FALSE_SAFE", "FALSE_REVIEW", "TRUE_SAFE")


def load_cases() -> list[dict]:
    return json.loads((BENCH / "cases.json").read_text())


def run_one(case: dict, k: int, client) -> dict:
    from blastguard_ai.loop import run_remediation
    text = (BENCH / case["file"]).read_text()
    try:
        res = run_remediation(text, client, max_wall_s=PER_RUN_WALL_S)
    except Exception as exc:  # record, never hide
        return {"case": case["id"], "k": k, "harness_error": f"{exc.__class__.__name__}: {exc}"}
    last = res.attempts[-1] if res.attempts else {}
    vals = (last.get("verification") or {}).get("validators") or res.validators_initial
    oracle = evaluate(ORACLES[case["id"]], text, res.final_yaml) if not ORACLES[case["id"]].get("invalid_input") \
        else {"verdict": "no_patch", "failed": [], "checks": 0}
    cand_oracle = None
    if res.final_yaml is None and res.last_candidate and not ORACLES[case["id"]].get("invalid_input"):
        cand_oracle = evaluate(ORACLES[case["id"]], text, res.last_candidate)
    return {
        "case": case["id"], "k": k, "category": case["category"], "model": res.model,
        "status": res.status, "initial_status": res.initial_status, "release": res.release, "error": res.error,
        "attempts": len(res.attempts), "llm_calls": len(res.attempts), "tokens": res.totals(), "wall_s": res.wall_s,
        "over_wall_budget": res.wall_s > PER_RUN_WALL_S,
        "validators": [{"name": v.get("name"), "status": v.get("status")} for v in vals],
        "attempt_summaries": [{"attempt": a.get("attempt"), "ok": (a.get("verification") or {}).get("ok"),
                               "error": a.get("error"),
                               "parse_error": (a.get("verification") or {}).get("parse_error"),
                               "guard": (a.get("verification") or {}).get("guard"),
                               "failed_validators": [v.get("name") for v in (a.get("verification") or {}).get("validators", [])
                                                     if v.get("status") == "fail"],
                               "blocking": [f["rule_id"] for f in (a.get("verification") or {}).get("findings", [])
                                            if f.get("blocking")],
                               "rationale": a.get("rationale")} for a in res.attempts],
        "intent_verdict": (res.intent or {}).get("verdict"),
        "drift_codes": [d["code"] for d in (res.intent or {}).get("drifts", [])],
        "oracle": oracle, "last_candidate_oracle": cand_oracle,
        "final_yaml": res.final_yaml, "last_candidate": res.last_candidate, "diff": res.diff,
        "timestamp": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def classify(r: dict) -> str | None:
    if r.get("status") != "VERIFIED" or r.get("attempts", 0) == 0:
        return None
    broken = r["oracle"]["verdict"] == "broken"
    safe = r["release"] == "SAFE_TO_PROPOSE"
    return {(True, False): "TRUE_REVIEW", (True, True): "FALSE_SAFE",
            (False, False): "FALSE_REVIEW", (False, True): "TRUE_SAFE"}[(broken, safe)]


def _diff(a: str, b: str | None, n: int = 60) -> str:
    lines = list(difflib.unified_diff(a.splitlines(True), (b or "").splitlines(True), "original", "patched", n=1))
    return "".join(lines[:n]) + ("...\n" if len(lines) > n else "")


def aggregate(cases: list[dict]) -> dict:
    runs = [json.loads(p.read_text()) for p in sorted(RAW.glob("*.json"))]
    by_case = {c["id"]: [r for r in runs if r["case"] == c["id"]] for c in cases}
    matrix = {m: 0 for m in MATRIX}
    for r in runs:
        r["cell"] = classify(r)
        if r["cell"]:
            matrix[r["cell"]] += 1
    tok = [r["tokens"]["total_tokens"] for r in runs if r.get("llm_calls")]
    wall = [r["wall_s"] for r in runs if "wall_s" in r]
    summary = {
        "n_runs": len(runs),
        "model": next((r["model"] for r in runs if r.get("model")), None),
        "matrix": matrix, "n_matrix": sum(matrix.values()),
        "status_counts": {}, "release_counts": {},
        "harness_errors": sum(1 for r in runs if r.get("harness_error")),
        "api_errors": sum(1 for r in runs if (r.get("error") or "").startswith("LLM API error")),
        "llm_calls": sum(r.get("llm_calls", 0) for r in runs),
        "retries": sum(max(0, r.get("attempts", 0) - 1) for r in runs),
        "tokens_total": sum(r.get("tokens", {}).get("total_tokens", 0) for r in runs),
        "prompt_tokens": sum(r.get("tokens", {}).get("prompt_tokens", 0) for r in runs),
        "completion_tokens": sum(r.get("tokens", {}).get("completion_tokens", 0) for r in runs),
        "tokens_median": statistics.median(tok) if tok else 0, "tokens_max": max(tok) if tok else 0,
        "wall_median": statistics.median(wall) if wall else 0, "wall_max": max(wall) if wall else 0,
        "over_wall_budget": sum(1 for r in runs if r.get("over_wall_budget")),
    }
    for r in runs:
        for key, field in (("status_counts", "status"), ("release_counts", "release")):
            v = r.get(field, "HARNESS_ERROR")
            summary[key][v] = summary[key].get(v, 0) + 1
    per_case = []
    for c in cases:
        rs = by_case[c["id"]]
        per_case.append({"id": c["id"], "category": c["category"], "n": len(rs),
                         "status": [r.get("status") for r in rs], "release": [r.get("release") for r in rs],
                         "oracle": [r.get("oracle", {}).get("verdict") for r in rs],
                         "cells": [r.get("cell") for r in rs], "attempts": [r.get("attempts") for r in rs],
                         "drifts": sorted({d for r in rs for d in r.get("drift_codes", [])}),
                         "oracle_failed": sorted({f for r in rs for f in r.get("oracle", {}).get("failed", [])})})
    return {"summary": summary, "per_case": per_case, "runs": runs}


def write_reports(cases: list[dict], agg: dict) -> None:
    s = agg["summary"]
    runs = agg["runs"]
    out = {"summary": s, "per_case": agg["per_case"],
           "runs": [{k: v for k, v in r.items() if k not in ("final_yaml", "last_candidate", "diff")} for r in runs]}
    (BENCH / "results" / "results.json").write_text(json.dumps(out, indent=2) + "\n")
    dates = sorted(r["timestamp"][:10] for r in runs if r.get("timestamp"))
    m = s["matrix"]
    L = ["# BlastGuard AI benchmark results", "",
         f"- Model: `{s['model']}` (NVIDIA Nemotron via Nebius Token Factory)",
         f"- Date of runs: {dates[0] if dates else '?'}{' to ' + dates[-1] if dates and dates[-1] != dates[0] else ''}",
         f"- Total runs: n={s['n_runs']} ({len(cases)} cases); LLM calls: {s['llm_calls']}",
         CORPUS_NOTE, "",
         "## Corpus", "",
         "| id | category | secure+functional fix possible | expected |", "|---|---|---|---|"]
    for c in cases:
        L.append(f"| {c['id']} | {c['category']} | {c['secure_and_functional_possible']} | {c['expected_outcome']} |")
    L += ["", "Function ground truth comes from `benchmark/oracles.py`, which is plain-dict logic written independently "
          "of `blastguard_ai/intent.py` (it does not import it). Oracles check declared function only (hostPath/hostNetwork/"
          "kernel access/Service type where the workload needs them, command/args/env/ports/probes, image repo, replicas, "
          "declared writable paths under a read-only root FS, memory floors, added NetworkPolicies not cutting declared "
          "traffic). They are static: they cannot prove the app runs in a cluster.", "",
          "Caveat: the oracles are independent in code but not in concept. Several of their checks (hostPath, hostNetwork, "
          "Service type, privileged/caps) test the same structural facts the gate tests, so agreement on the "
          "function-critical cases is expected. The matrix shows the gate is consistent with an independent "
          "re-implementation on these 16 cases; it does not show the gate catches breakage outside what both encode.", "",
          "## Per-case results", "",
          "| case | n | status | release | oracle | matrix cell | attempts | intent drift codes | oracle failures |",
          "|---|---|---|---|---|---|---|---|---|"]
    for p in agg["per_case"]:
        L.append(f"| {p['id']} | {p['n']} | {', '.join(map(str, p['status']))} | {', '.join(map(str, p['release']))} | "
                 f"{', '.join(map(str, p['oracle']))} | {', '.join(str(x or '-') for x in p['cells'])} | "
                 f"{', '.join(map(str, p['attempts']))} | {', '.join(p['drifts']) or '-'} | "
                 f"{'; '.join(p['oracle_failed']) or '-'} |")
    hard = [r for r in runs if r.get("status") == "VERIFIED" and r.get("attempts", 0) == 0]
    L += ["", "## Confusion matrix (runs that reached VERIFIED after a model patch)", "",
          f"n = {s['n_matrix']} runs (out of {s['n_runs']}).", "",
          "| | gate REVIEW_REQUIRED | gate SAFE_TO_PROPOSE |", "|---|---|---|",
          f"| oracle: function broken | TRUE_REVIEW = {m['TRUE_REVIEW']} | **FALSE_SAFE = {m['FALSE_SAFE']}** |",
          f"| oracle: function preserved | FALSE_REVIEW = {m['FALSE_REVIEW']} | TRUE_SAFE = {m['TRUE_SAFE']} |", "",
          f"Already-hardened inputs (VERIFIED with 0 attempts, not in the matrix): n={len(hard)}; release values: "
          f"{sorted({r['release'] for r in hard})}. The loop returns the original unchanged and reports "
          "NO_CHANGE_NEEDED when every external validator passed on the input (no patch to judge).", "",
          "## Not proposed / unresolved", "",
          f"- status counts over n={s['n_runs']}: {s['status_counts']}",
          f"- release counts over n={s['n_runs']}: {s['release_counts']}",
          f"- LLM API errors: {s['api_errors']}; harness errors: {s['harness_errors']}; runs over the "
          f"{PER_RUN_WALL_S:.0f}s budget: {s['over_wall_budget']}", ""]
    unres = [r for r in runs if r.get("status") == "UNRESOLVED" and r.get("last_candidate_oracle")]
    if unres:
        L.append("UNRESOLVED runs whose last (unverified, not proposed) candidate was scored by the oracle:")
        for r in unres:
            L.append(f"- {r['case']}#{r['k']}: candidate oracle={r['last_candidate_oracle']['verdict']}; "
                     f"last blocking={r['attempt_summaries'][-1]['blocking'] if r['attempt_summaries'] else '-'}")
        L.append("")
    L += ["## Hostile / invalid inputs", ""]
    for r in runs:
        if r.get("category") == "hostile":
            L.append(f"- {r['case']}#{r['k']}: status={r['status']} release={r['release']} llm_calls={r['llm_calls']} "
                     f"error={r.get('error')} oracle={r['oracle']['verdict']} {r['oracle']['failed'] or ''}")
    L += ["", "No case is ever executed: the model output is parsed as YAML data and passed to static validators only.",
          "", "## Retries, tokens, time", "",
          f"- Retries (attempts beyond the first) summed over n={s['n_runs']} runs: {s['retries']}",
          f"- Attempts per run: " + ", ".join(f"{a}: {sum(1 for r in runs if r.get('attempts') == a)}"
                                              for a in sorted({r.get('attempts', 0) for r in runs})),
          f"- Tokens per run with at least one LLM call: median {s['tokens_median']}, max {s['tokens_max']}",
          f"- Total tokens: {s['tokens_total']} (prompt {s['prompt_tokens']}, completion {s['completion_tokens']})",
          f"- Wall time per run: median {s['wall_median']:.1f}s, max {s['wall_max']:.1f}s", "",
          "## Every FALSE_SAFE", ""]
    fs = [r for r in runs if r.get("cell") == "FALSE_SAFE"]
    if not fs:
        L.append(f"None on this corpus (n={s['n_matrix']} VERIFIED runs).")
    for r in fs:
        L += [f"### {r['case']} run {r['k']}", f"Oracle failures: {r['oracle']['failed']}; intent drifts: "
              f"{r['drift_codes']}", "", "```diff", _diff((BENCH / next(c['file'] for c in cases
                                                                         if c['id'] == r['case'])).read_text(),
                                                           r["final_yaml"]).rstrip(), "```", ""]
    L += ["", "## Every FALSE_REVIEW", ""]
    fr = [r for r in runs if r.get("cell") == "FALSE_REVIEW"]
    if not fr:
        L.append("None on this corpus.")
    for r in fr:
        L.append(f"- {r['case']}#{r['k']}: high/other drifts {r['drift_codes']}; validators "
                 f"{[(v['name'], v['status']) for v in r['validators']]}")
    (BENCH / "results" / "RESULTS.md").write_text("\n".join(L) + "\n")


def _use_blind_suite() -> None:
    """Point the runner at benchmark/blind/ (cases, oracles, results) without changing the default suite."""
    global BENCH, RAW, ORACLES, evaluate, MAX_TOTAL_RUNS, CORPUS_NOTE
    from benchmark.blind import oracles as blind_oracles
    BENCH = ROOT / "benchmark" / "blind"
    RAW = BENCH / "results" / "raw"
    ORACLES, evaluate = blind_oracles.ORACLES, blind_oracles.evaluate
    MAX_TOTAL_RUNS = 40
    CORPUS_NOTE = ("- BLIND suite. All statements below hold **on this corpus** only: 6 cases written by one author "
                   "without reading the gate, scored by static oracles in `benchmark/blind/oracles.py`; no cluster run. "
                   "The per-run `Corpus` caveat paragraph below describes the main suite's oracles, not these.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--offline", action="store_true", help="replay saved raw JSON, no API calls")
    ap.add_argument("--cases", default="", help="comma-separated id prefixes")
    ap.add_argument("--only-failed", action="store_true", help="rerun only raw runs with API/harness errors")
    ap.add_argument("--suite", choices=("main", "blind"), default="main")
    args = ap.parse_args()
    if args.suite == "blind":
        _use_blind_suite()
    cases = load_cases()
    RAW.mkdir(parents=True, exist_ok=True)
    if not args.offline:
        from blastguard_ai.llm import LLMError, NebiusClient
        try:
            client = NebiusClient()
        except LLMError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        sel = [c for c in cases if not args.cases or any(c["id"].startswith(p) for p in args.cases.split(","))]
        jobs = [(c, k) for c in sel for k in range(1, args.repeats + 1)]
        if args.only_failed:
            def bad(c, k):
                p = RAW / f"{c['id']}-{k}.json"
                if not p.exists():
                    return True
                r = json.loads(p.read_text())
                return bool(r.get("harness_error") or (r.get("error") or "").startswith("LLM API error"))
            jobs = [(c, k) for c, k in jobs if bad(c, k)]
        if len(jobs) > MAX_TOTAL_RUNS:
            print(f"refusing: {len(jobs)} runs > cap {MAX_TOTAL_RUNS}", file=sys.stderr)
            return 2
        for c, k in jobs:
            r = run_one(c, k, client)
            (RAW / f"{c['id']}-{k}.json").write_text(json.dumps(r, indent=2) + "\n")
            print(f"{c['id']}#{k}: {r.get('status')} {r.get('release')} attempts={r.get('attempts')} "
                  f"oracle={r.get('oracle', {}).get('verdict')} wall={r.get('wall_s')} err={r.get('error') or r.get('harness_error')}",
                  flush=True)
    agg = aggregate(cases)
    write_reports(cases, agg)
    print(json.dumps(agg["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
