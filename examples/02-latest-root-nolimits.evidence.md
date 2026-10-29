# BlastGuard AI evidence report

- Source: `02-latest-root-nolimits.yaml`
- Model: `nvidia/nemotron-3-super-120b-a12b`
- Status: **BLOCKED -> VERIFIED**
- Attempts: 1  |  Wall time: 2.91s  |  Tokens: 1403 (prompt 997, completion 406)

## Initial findings

| Rule | Severity | Object | Container | Message |
|---|---|---|---|---|
| BG011 | medium | Deployment/payments/payments-api | - | Service account token automounted: set automountServiceAccountToken: false unless the API is needed |
| BG005 | high | Deployment/payments/payments-api | api | May run as root (runAsNonRoot not true or runAsUser 0) |
| BG006 | high | Deployment/payments/payments-api | api | allowPrivilegeEscalation not explicitly false |
| BG007 | medium | Deployment/payments/payments-api | api | Missing CPU/memory limits: missing cpu,memory |
| BG008 | medium | Deployment/payments/payments-api | api | Image uses :latest or has no tag/digest: nginx:latest |
| BG009 | medium | Deployment/payments/payments-api | api | readOnlyRootFilesystem not true |
| BG013 | info | bundle | - | No NetworkPolicy in this manifest bundle: consider a default-deny NetworkPolicy |

Initial validators: kubeconform=pass, kube-linter=fail

## Attempt 1
- Channel: tool_call  |  LLM latency: 2.74s  |  tokens: 1403
- Verification: PASS
- Remaining blocking findings: 0
- kubeconform: pass
- kube-linter: pass
- Model rationale:

> Fixed automountServiceAccountToken, runAsNonRoot with non-zero UID, disabled privilege escalation, added CPU/memory limits/requests, pinned image tag, set readOnlyRootFilesystem.

## Verified diff

```diff
--- original.yaml
+++ patched.yaml
@@ -1,4 +1,3 @@
-# API deployment: floating image tag, runs as root, unbounded resources.
 apiVersion: apps/v1
 kind: Deployment
 metadata:
@@ -14,10 +13,21 @@
       labels:
         app: payments-api
     spec:
+      automountServiceAccountToken: false
       containers:
         - name: api
-          image: nginx:latest
+          image: nginx:1.23
           ports:
             - containerPort: 8080
           securityContext:
-            runAsUser: 0
+            runAsNonRoot: true
+            runAsUser: 1000
+            allowPrivilegeEscalation: false
+            readOnlyRootFilesystem: true
+          resources:
+            limits:
+              cpu: "100m"
+              memory: "128Mi"
+            requests:
+              cpu: "50m"
+              memory: "64Mi"
```
