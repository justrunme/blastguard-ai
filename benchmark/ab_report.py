"""A/B counterfactual from saved benchmark runs (no model calls): security-only vs BlastGuard with the gate."""
import glob
import json
from pathlib import Path

root = Path(__file__).parent
rows = [json.load(open(f)) for f in sorted(glob.glob(str(root / "results/raw/*.json")))]
v = [r for r in rows if r["status"] == "VERIFIED" and r["attempts"] > 0]
broken = [r for r in v if r["oracle"]["verdict"] == "broken"]
good = [r for r in v if r["oracle"]["verdict"] == "preserved"]
n = len(v)
bg_safe = len([r for r in broken if r["release"] == "SAFE_TO_PROPOSE"])
bg_rev = len([r for r in broken if r["release"] == "REVIEW_REQUIRED"])
good_rev = len([r for r in good if r["release"] == "REVIEW_REQUIRED"])
md = f"""# A/B counterfactual: security-only vs BlastGuard (on this corpus)

Baseline: a security-only tool accepts every patch that passes the policy checks and external validators.
BlastGuard additionally runs the Intent Preservation Gate. No new model calls: this re-reads the {n} saved runs
in `benchmark/results/raw/` that reached VERIFIED after a model patch (ground truth: static oracles in
`benchmark/oracles.py`; 16 hand-written cases, 3 runs each). Regenerate with `python benchmark/ab_report.py`.

| Metric (n = {n} verified patches) | Security-only | BlastGuard |
|---|---|---|
| Patches that break the declared function but are accepted as safe | {len(broken)} | {bg_safe} |
| Patches that break the declared function and are sent to human review | 0 | {bg_rev} |
| Function-preserving patches sent to review unnecessarily | 0 | {good_rev} |

Limits: static oracles, not cluster runs; the oracle and the gate encode overlapping structural facts; small
corpus. Read it as "on this corpus", not as a general detection rate.
"""
(root / "results/AB.md").write_text(md)
print(md)
