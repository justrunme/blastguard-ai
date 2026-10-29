# BlastGuard AI evidence report

- Source: `04-stateless-api-missing-limits.yaml`
- Model: `nvidia/nemotron-3-super-120b-a12b`
- Status: **BLOCKED -> VERIFIED**
- Attempts: 2  |  Wall time: 5.93s  |  Tokens: 2948 (prompt 2051, completion 897)
- Release decision: **SAFE_TO_PROPOSE**

## Initial findings

| Rule | Severity | Object | Container | Message |
|---|---|---|---|---|
| BG011 | medium | Deployment/orders/orders-api | - | Service account token automounted: set automountServiceAccountToken: false unless the API is needed |
| BG006 | high | Deployment/orders/orders-api | api | allowPrivilegeEscalation not explicitly false |
| BG007 | medium | Deployment/orders/orders-api | api | Missing CPU/memory limits: missing cpu,memory |
| BG013 | info | bundle | - | No NetworkPolicy in this manifest bundle: consider a default-deny NetworkPolicy |

Initial validators: kubeconform=pass, kube-linter=fail

## Attempt 1
- Channel: tool_call  |  LLM latency: 2.11s  |  tokens: 1361
- Verification: FAIL
- Remaining blocking findings: 0
- kubeconform: pass
- kube-linter: fail (1 issues)
- Model rationale:

> Added automountServiceAccountToken: false, set allowPrivilegeEscalation: false, added CPU/memory limits.

## Attempt 2
- Channel: tool_call  |  LLM latency: 3.58s  |  tokens: 1587
- Verification: PASS
- Remaining blocking findings: 0
- kubeconform: pass
- kube-linter: pass
- Model rationale:

> Added CPU and memory requests to satisfy resource requirements; kept existing limits and other security settings unchanged.

## Intent Preservation Gate

Verdict: **NO_HIGH_IMPACT_DRIFT**. No high-impact static drift detected. Behaviour in a cluster is still not proven.

| Severity | Code | Object | What changed |
|---|---|---|---|
| medium | SA_TOKEN_DISABLED | Deployment/orders/orders-api | service account token is no longer mounted: breaks the app if it calls the Kubernetes API |
| info | LIMITS_ADDED | Deployment/orders/orders-api container 'api' | resource limits added: too-low values cause OOMKills or CPU throttling |

## Verified diff

```diff
--- original.yaml
+++ patched.yaml
@@ -15,6 +15,7 @@
       labels:
         app: orders-api
     spec:
+      automountServiceAccountToken: false
       containers:
         - name: api
           image: ghcr.io/example/orders-api:1.4.2
@@ -24,9 +25,17 @@
             runAsNonRoot: true
             runAsUser: 10001
             readOnlyRootFilesystem: true
+            allowPrivilegeEscalation: false
           volumeMounts:
             - name: tmp
               mountPath: /tmp
+          resources:
+            limits:
+              cpu: "500m"
+              memory: "256Mi"
+            requests:
+              cpu: "250m"
+              memory: "128Mi"
       volumes:
         - name: tmp
-          emptyDir: {}
+          emptyDir: {}
```
