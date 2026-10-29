# Post-hoc audit of blind-suite REVIEW_REQUIRED calls (b02, b03, b05)

**Scope.** After the blind run, a manual reading (end of `benchmark/blind/results/RESULTS.md`) suggested the
frozen oracles were too lax for three cases they marked `preserved`. This audit tests those suspicions on a
disposable kind cluster in GitHub Actions. It does **not** change the frozen oracles, the published matrix, the gate,
or any published number. No new model calls were made; the patched manifests are the stored `final_yaml` from
`benchmark/blind/results/raw/*.json`.

**Run:** https://github.com/justrunme/blastguard-ai/actions/runs/40816573846 (workflow `blind-audit`, artifact
`blind-audit-result` = `audit-result.json`). An earlier run (40815797571) gave the same b03/b05 results; its b02
pod step had a test bug (pod names with dots), fixed before the run above.

Reproduce: `.github/workflows/blind-audit.yml` → `audit/run_audit.sh`, manifests in `audit/manifests/`.

## Summary

| Case | Suspicion | Classification |
|---|---|---|
| b03 nginx + reloader | read-only root FS, no writable `/tmp` → nginx fails | **CONFIRMED BREAK** (3/3 patched runs) |
| b05 kubectl CronJob | projected token without `ca.crt` → kubectl fails | **CONFIRMED BREAK** (3/3 patched runs) |
| b02 `:latest` → invented tag | `v1.2.3` / `v1.0.0` may not exist | **NOT CONFIRMED** (not testable: the registry is fictional) |

## b03 — nginx-unprivileged:1.25.4, `readOnlyRootFilesystem: true`

Setup: original case manifest and the 3 patched `final_yaml` (all 3 distinct, so none deduplicated), `replicas: 1`.
A synthetic ConfigMap `edge-proxy-conf` (`listen 8080; return 200 "AUDIT_OK"`) was added because the case references it.
The sidecar image `registry.example.com/conf-reloader:2.1.0` is fictional and never pulls (in the original too),
so only the **nginx container** is judged; pod-level Ready is never reachable for any variant.

| Variant | nginx container | restarts after ~60 s | HTTP GET :8080 |
|---|---|---|---|
| original | running, ready | 0 | `AUDIT_OK` |
| patched run 1 | CrashLoopBackOff, exit 1 | 3 | connection refused |
| patched run 2 | terminated (Error), exit 1 | 3 | connection refused |
| patched run 3 | terminated (Error), exit 1 | 3 | connection refused |

Observed nginx log (identical in all three patched runs):

```
10-listen-on-ipv6-by-default.sh: info: can not modify /etc/nginx/conf.d/default.conf (read-only file system?)
nginx: [emerg] mkdir() "/tmp/proxy_temp" failed (30: Read-only file system)
```

Not tested: whether the reloader can signal nginx (sidecar image does not exist).

## b05 — `kubectl delete pods --field-selector=status.phase==Succeeded -A`

Setup: a Job built from each CronJob's `jobTemplate` verbatim, plus a synthetic ServiceAccount `pod-janitor` with a
ClusterRole (pods: get/list/delete) as the case implies, and a seed pod in phase Succeeded. One substitution:
`bitnami/kubectl:1.29.2` returns 404 on Docker Hub (Bitnami moved old tags), so all variants, original included,
use `bitnamilegacy/kubectl:1.29.2` (same tag).

| Variant | Job | seed pod |
|---|---|---|
| original | succeeded=1 | deleted |
| patched run 1 | failed=1 | still present |
| patched run 2 (`audience: api`) | failed=1 | still present |
| patched run 3 (`audience: api`) | failed=1 | still present |

Observed log (same shape in all three patched runs):

```
E1029 ... config.go:529] Expected to load root CA config from /var/run/secrets/kubernetes.io/serviceaccount/ca.crt, but got err: open /var/run/secrets/kubernetes.io/serviceaccount/ca.crt: no such file or directory
Unable to connect to the server: tls: failed to verify certificate: x509: certificate signed by unknown authority
```

The failure happens at TLS, before the token is sent, so this audit says nothing about whether `audience: api` would
also be rejected. The original Job's log came back empty in the capture; its success is shown by the Job status and
the seed pod being deleted.

## b02 — `registry.example.com/ledger-api`

Registry HTTP API (`curl .../v2/ledger-api/manifests/<tag>`) and a kubelet pull for `latest`, `v1.2.3`, `v1.0.0`:
all three fail the same way (`curl` exit 6; `lookup registry.example.com ... no such host`, ErrImagePull /
ImagePullBackOff). The registry is a placeholder in the case, so the original `:latest` cannot be pulled either.
Whether the invented tags exist **cannot be determined**; this stays NOT CONFIRMED. The read-only root FS concern for
b02 was not tested (no real image).

## Limits

- Post-hoc: the suspicions came from reading the outputs after the run; one author picked and ran the tests.
- Small: 3 cases, 3 runs each, a single kind node on `ubuntu-latest`, one run per variant.
- Synthetic scaffolding (ConfigMap, RBAC, seed pod) and one image substitution (b05) were added by the auditor.
- The frozen oracle matrix in `benchmark/blind/results/RESULTS.md` is unchanged. Under it, these cells remain
  FALSE_REVIEW; this audit only shows that for b03 and b05 the Gate's REVIEW_REQUIRED matched an observed runtime break.
