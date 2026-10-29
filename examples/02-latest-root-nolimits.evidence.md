# BlastGuard AI evidence report

- Source: `02-latest-root-nolimits.yaml`
- Model: `nvidia/nemotron-3-super-120b-a12b`
- Status: **BLOCKED -> VERIFIED**
- Attempts: 1  |  Wall time: 3.22s  |  Tokens: 1414 (prompt 997, completion 417)
- Release decision: **REVIEW_REQUIRED**

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
- Channel: tool_call  |  LLM latency: 3.07s  |  tokens: 1414
- Verification: PASS
- Remaining blocking findings: 0
- kubeconform: pass
- kube-linter: pass
- Model rationale:

> Fixed findings: set automountServiceAccountToken false, changed image tag to specific version, added runAsNonRoot true with non-zero user, set allowPrivilegeEscalation false, readOnlyRootFilesystem true, added CPU/memory limits and requests.

## Intent Preservation Gate

Verdict: **REVIEW_REQUIRED**. A security-clean patch changed what the workload does. Review before proposing.

| Severity | Code | Object | What changed |
|---|---|---|---|
| medium | SA_TOKEN_DISABLED | Deployment/payments/payments-api | service account token is no longer mounted: breaks the app if it calls the Kubernetes API |
| medium | IMAGE_TAG_CHANGED | Deployment/payments/payments-api container 'api' | image tag changed latest -> 1.25.3: behaviour depends on what that tag contains |
| medium | USER_CHANGED | Deployment/payments/payments-api container 'api' | now runs as non-root (runAsUser 1000): the image must support that user |
| high | ROOTFS_READONLY_NO_WRITABLE_PATH | Deployment/payments/payments-api container 'api' | root filesystem is read-only and no writable volume is mounted: apps that write temp/log/cache files will crash |
| info | LIMITS_ADDED | Deployment/payments/payments-api container 'api' | resource limits added: too-low values cause OOMKills or CPU throttling |

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
+          image: nginx:1.25.3
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
+              cpu: "500m"
+              memory: "256Mi"
+            requests:
+              cpu: "250m"
+              memory: "128Mi"
```
