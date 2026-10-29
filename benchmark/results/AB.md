# A/B counterfactual: security-only vs BlastGuard (on this corpus)

Baseline: a security-only tool accepts every patch that passes the policy checks and external validators.
BlastGuard additionally runs the Intent Preservation Gate. No new model calls: this re-reads the 35 saved runs
in `benchmark/results/raw/` that reached VERIFIED after a model patch (ground truth: static oracles in
`benchmark/oracles.py`; 16 hand-written cases, 3 runs each). Regenerate with `python benchmark/ab_report.py`.

| Metric (n = 35 verified patches) | Security-only | BlastGuard |
|---|---|---|
| Patches that break the declared function but are accepted as safe | 14 | 0 |
| Patches that break the declared function and are sent to human review | 0 | 14 |
| Function-preserving patches sent to review unnecessarily | 0 | 0 |

Limits: static oracles, not cluster runs; the oracle and the gate encode overlapping structural facts; small
corpus. Read it as "on this corpus", not as a general detection rate.
