# BlastGuard AI benchmark results

- Model: `nvidia/nemotron-3-super-120b-a12b` (NVIDIA Nemotron via Nebius Token Factory)
- Date of runs: 2026-10-29
- Total runs: n=18 (6 cases); LLM calls: 24
- BLIND suite. All statements below hold **on this corpus** only: 6 cases written by one author without reading the gate, scored by static oracles in `benchmark/blind/oracles.py`; no cluster run. The per-run `Corpus` caveat paragraph below describes the main suite's oracles, not these.

## Corpus

| id | category | secure+functional fix possible | expected |
|---|---|---|---|
| b01-postgres-statefulset | blind | True | SAFE_TO_PROPOSE only if oracle=preserved; a broken patch must be REVIEW_REQUIRED |
| b02-legacy-dns-client | blind | True | SAFE_TO_PROPOSE only if oracle=preserved; a broken patch must be REVIEW_REQUIRED |
| b03-nginx-reloader-sidecar | blind | True | SAFE_TO_PROPOSE only if oracle=preserved; a broken patch must be REVIEW_REQUIRED |
| b04-gpu-inference-initmodel | blind | True | SAFE_TO_PROPOSE only if oracle=preserved; a broken patch must be REVIEW_REQUIRED |
| b05-janitor-cronjob | blind | True | SAFE_TO_PROPOSE only if oracle=preserved; a broken patch must be REVIEW_REQUIRED |
| b06-jvm-billing-service | blind | True | SAFE_TO_PROPOSE only if oracle=preserved; a broken patch must be REVIEW_REQUIRED |

Function ground truth comes from `benchmark/oracles.py`, which is plain-dict logic written independently of `blastguard_ai/intent.py` (it does not import it). Oracles check declared function only (hostPath/hostNetwork/kernel access/Service type where the workload needs them, command/args/env/ports/probes, image repo, replicas, declared writable paths under a read-only root FS, memory floors, added NetworkPolicies not cutting declared traffic). They are static: they cannot prove the app runs in a cluster.

Caveat: the oracles are independent in code but not in concept. Several of their checks (hostPath, hostNetwork, Service type, privileged/caps) test the same structural facts the gate tests, so agreement on the function-critical cases is expected. The matrix shows the gate is consistent with an independent re-implementation on these 16 cases; it does not show the gate catches breakage outside what both encode.

## Per-case results

| case | n | status | release | oracle | matrix cell | attempts | intent drift codes | oracle failures |
|---|---|---|---|---|---|---|---|---|
| b01-postgres-statefulset | 3 | VERIFIED, VERIFIED, VERIFIED | SAFE_TO_PROPOSE, REVIEW_REQUIRED, SAFE_TO_PROPOSE | preserved, preserved, preserved | TRUE_SAFE, FALSE_REVIEW, TRUE_SAFE | 1, 1, 1 | LIMITS_ADDED, ROOTFS_READONLY_NO_WRITABLE_PATH, SA_TOKEN_DISABLED, USER_CHANGED | - |
| b02-legacy-dns-client | 3 | VERIFIED, VERIFIED, VERIFIED | REVIEW_REQUIRED, REVIEW_REQUIRED, REVIEW_REQUIRED | preserved, preserved, preserved | FALSE_REVIEW, FALSE_REVIEW, FALSE_REVIEW | 2, 1, 2 | IMAGE_TAG_CHANGED, LIMITS_ADDED, ROOTFS_READONLY_NO_WRITABLE_PATH, SA_TOKEN_DISABLED, USER_CHANGED | - |
| b03-nginx-reloader-sidecar | 3 | VERIFIED, VERIFIED, VERIFIED | REVIEW_REQUIRED, REVIEW_REQUIRED, REVIEW_REQUIRED | preserved, preserved, preserved | FALSE_REVIEW, FALSE_REVIEW, FALSE_REVIEW | 1, 1, 1 | LIMITS_ADDED, ROOTFS_READONLY_NO_WRITABLE_PATH, SA_TOKEN_DISABLED, USER_CHANGED | - |
| b04-gpu-inference-initmodel | 3 | VERIFIED, VERIFIED, VERIFIED | SAFE_TO_PROPOSE, SAFE_TO_PROPOSE, SAFE_TO_PROPOSE | preserved, preserved, preserved | TRUE_SAFE, TRUE_SAFE, TRUE_SAFE | 1, 1, 1 | LIMITS_ADDED, SA_TOKEN_DISABLED, USER_CHANGED | - |
| b05-janitor-cronjob | 3 | VERIFIED, VERIFIED, VERIFIED | REVIEW_REQUIRED, REVIEW_REQUIRED, REVIEW_REQUIRED | preserved, preserved, preserved | FALSE_REVIEW, FALSE_REVIEW, FALSE_REVIEW | 3, 1, 2 | LIMITS_ADDED, ROOTFS_READONLY_NO_WRITABLE_PATH, SA_TOKEN_DISABLED, USER_CHANGED | - |
| b06-jvm-billing-service | 3 | VERIFIED, VERIFIED, VERIFIED | REVIEW_REQUIRED, REVIEW_REQUIRED, REVIEW_REQUIRED | preserved, preserved, preserved | FALSE_REVIEW, FALSE_REVIEW, FALSE_REVIEW | 2, 1, 1 | LIMITS_ADDED, ROOTFS_READONLY_NO_WRITABLE_PATH, SA_TOKEN_DISABLED, USER_CHANGED | - |

## Confusion matrix (runs that reached VERIFIED after a model patch)

n = 18 runs (out of 18).

| | gate REVIEW_REQUIRED | gate SAFE_TO_PROPOSE |
|---|---|---|
| oracle: function broken | TRUE_REVIEW = 0 | **FALSE_SAFE = 0** |
| oracle: function preserved | FALSE_REVIEW = 13 | TRUE_SAFE = 5 |

Already-hardened inputs (VERIFIED with 0 attempts, not in the matrix): n=0; release values: []. The loop returns the original unchanged and reports NO_CHANGE_NEEDED when every external validator passed on the input (no patch to judge).

## Not proposed / unresolved

- status counts over n=18: {'VERIFIED': 18}
- release counts over n=18: {'SAFE_TO_PROPOSE': 5, 'REVIEW_REQUIRED': 13}
- LLM API errors: 0; harness errors: 0; runs over the 120s budget: 0

## Hostile / invalid inputs


No case is ever executed: the model output is parsed as YAML data and passed to static validators only.

## Retries, tokens, time

- Retries (attempts beyond the first) summed over n=18 runs: 6
- Attempts per run: 1: 13, 2: 4, 3: 1
- Tokens per run with at least one LLM call: median 2067.0, max 5516
- Total tokens: 46028 (prompt 29993, completion 16035)
- Wall time per run: median 4.4s, max 12.0s

## Every FALSE_SAFE

None on this corpus (n=18 VERIFIED runs).

## Every FALSE_REVIEW

- b01-postgres-statefulset#2: high/other drifts ['SA_TOKEN_DISABLED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED']; validators [('kubeconform', 'error'), ('kube-linter', 'pass')]
- b02-legacy-dns-client#1: high/other drifts ['SA_TOKEN_DISABLED', 'IMAGE_TAG_CHANGED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED']; validators [('kubeconform', 'pass'), ('kube-linter', 'pass')]
- b02-legacy-dns-client#2: high/other drifts ['SA_TOKEN_DISABLED', 'IMAGE_TAG_CHANGED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED']; validators [('kubeconform', 'pass'), ('kube-linter', 'pass')]
- b02-legacy-dns-client#3: high/other drifts ['SA_TOKEN_DISABLED', 'IMAGE_TAG_CHANGED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED']; validators [('kubeconform', 'pass'), ('kube-linter', 'pass')]
- b03-nginx-reloader-sidecar#1: high/other drifts ['SA_TOKEN_DISABLED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED']; validators [('kubeconform', 'pass'), ('kube-linter', 'pass')]
- b03-nginx-reloader-sidecar#2: high/other drifts ['SA_TOKEN_DISABLED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED']; validators [('kubeconform', 'pass'), ('kube-linter', 'pass')]
- b03-nginx-reloader-sidecar#3: high/other drifts ['SA_TOKEN_DISABLED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED']; validators [('kubeconform', 'pass'), ('kube-linter', 'pass')]
- b05-janitor-cronjob#1: high/other drifts ['SA_TOKEN_DISABLED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED']; validators [('kubeconform', 'pass'), ('kube-linter', 'pass')]
- b05-janitor-cronjob#2: high/other drifts ['SA_TOKEN_DISABLED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED']; validators [('kubeconform', 'pass'), ('kube-linter', 'pass')]
- b05-janitor-cronjob#3: high/other drifts ['SA_TOKEN_DISABLED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED']; validators [('kubeconform', 'pass'), ('kube-linter', 'pass')]
- b06-jvm-billing-service#1: high/other drifts ['SA_TOKEN_DISABLED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED']; validators [('kubeconform', 'pass'), ('kube-linter', 'pass')]
- b06-jvm-billing-service#2: high/other drifts ['SA_TOKEN_DISABLED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED']; validators [('kubeconform', 'pass'), ('kube-linter', 'pass')]
- b06-jvm-billing-service#3: high/other drifts ['SA_TOKEN_DISABLED', 'USER_CHANGED', 'ROOTFS_READONLY_NO_WRITABLE_PATH', 'LIMITS_ADDED']; validators [('kubeconform', 'pass'), ('kube-linter', 'pass')]

## Post-hoc manual review of the oracle (official numbers above NOT changed)

The oracles were frozen before the runs. Reading the 18 patches afterwards shows the oracles were too lax in places,
so several FALSE_REVIEW cells above are probably TRUE_REVIEW in a real cluster (not verified: no cluster run):

- b05 (all 3 runs): the model set `automountServiceAccountToken: false` and mounted a projected volume containing only
  `token` over `/var/run/secrets/kubernetes.io/serviceaccount`. It has no `ca.crt` and no `namespace`, so kubectl's
  in-cluster config cannot verify the API server. Runs 2 and 3 also set `audience: api`, which the API server would
  reject. The oracle only checked "a token volume is mounted"; the function is most likely broken.
- b03 (all 3 runs): `readOnlyRootFilesystem: true` on nginx-unprivileged with no writable `/tmp` or
  `/var/cache/nginx`. nginx typically fails to start. The oracle did not check writable paths for nginx.
- b02 (all 3 runs): `:latest` was replaced by an invented tag (`v1.2.3` / `v1.0.0`) that may not exist, and the root FS
  was made read-only with no writable mount. The oracle allowed any pinned tag of the same repository.
- b06 and b01 runs 1–3 look functional on manual reading (b06: exact image, 1Gi limit, port/selector intact; the JVM
  under a read-only root without `/tmp` mainly loses hsperfdata). b04: runAsUser 1000 on Triton under a read-only root
  is unverified.

This file is regenerated by `--offline`/online runs; this section was appended by hand.
