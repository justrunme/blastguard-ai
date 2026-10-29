# BlastGuard AI evidence report

- Source: `03-loadbalancer-exposed.yaml`
- Model: `nvidia/nemotron-3-super-120b-a12b`
- Status: **BLOCKED -> VERIFIED**
- Attempts: 1  |  Wall time: 2.79s  |  Tokens: 1547 (prompt 1083, completion 464)
- Release decision: **REVIEW_REQUIRED**

## Initial findings

| Rule | Severity | Object | Container | Message |
|---|---|---|---|---|
| BG003 | high | Deployment/internal/admin-panel | - | hostNetwork enabled |
| BG011 | medium | Deployment/internal/admin-panel | - | Service account token automounted: set automountServiceAccountToken: false unless the API is needed |
| BG005 | high | Deployment/internal/admin-panel | web | May run as root (runAsNonRoot not true or runAsUser 0) |
| BG006 | high | Deployment/internal/admin-panel | web | allowPrivilegeEscalation not explicitly false |
| BG007 | medium | Deployment/internal/admin-panel | web | Missing CPU/memory limits: missing cpu,memory |
| BG008 | medium | Deployment/internal/admin-panel | web | Image uses :latest or has no tag/digest: ghcr.io/example/admin-panel |
| BG009 | medium | Deployment/internal/admin-panel | web | readOnlyRootFilesystem not true |
| BG012 | high | Service/internal/admin-panel | - | Service exposed via LoadBalancer: use ClusterIP behind an Ingress/gateway |
| BG013 | info | bundle | - | No NetworkPolicy in this manifest bundle: consider a default-deny NetworkPolicy |

Initial validators: kubeconform=pass, kube-linter=fail

## Attempt 1
- Channel: tool_call  |  LLM latency: 2.63s  |  tokens: 1547
- Verification: PASS
- Remaining blocking findings: 0
- kubeconform: pass
- kube-linter: pass
- Model rationale:

> Disabled hostNetwork, set automountServiceAccountToken false, added securityContext (runAsNonRoot, non-zero runAsUser, allowPrivilegeEscalation false, readOnlyRootFilesystem), added CPU/Memory limits/requests, pinned image tag, changed Service type to ClusterIP.

## Intent Preservation Gate

Verdict: **REVIEW_REQUIRED**. A security-clean patch changed what the workload does. Review before proposing.

| Severity | Code | Object | What changed |
|---|---|---|---|
| high | HOSTNETWORK_REMOVED | Deployment/internal/admin-panel | hostNetwork was turned off: node IP and host ports are no longer used by the workload |
| medium | SA_TOKEN_DISABLED | Deployment/internal/admin-panel | service account token is no longer mounted: breaks the app if it calls the Kubernetes API |
| medium | IMAGE_TAG_CHANGED | Deployment/internal/admin-panel container 'web' | image tag changed latest -> v1.0.0: behaviour depends on what that tag contains |
| medium | USER_CHANGED | Deployment/internal/admin-panel container 'web' | now runs as non-root (runAsUser 1000): the image must support that user |
| medium | ROOTFS_READONLY_NO_WRITABLE_PATH | Deployment/internal/admin-panel container 'web' | root filesystem is read-only and no writable volume is mounted: apps that write temp/log/cache files will crash |
| info | LIMITS_ADDED | Deployment/internal/admin-panel container 'web' | resource limits added: too-low values cause OOMKills or CPU throttling |
| high | SERVICE_EXPOSURE_CHANGED | Service/internal/admin-panel | Service type LoadBalancer -> ClusterIP: clients outside the cluster can no longer reach it |

## Verified diff

```diff
--- original.yaml
+++ patched.yaml
@@ -14,12 +14,25 @@
       labels:
         app: admin-panel
     spec:
-      hostNetwork: true
+      hostNetwork: false
+      automountServiceAccountToken: false
       containers:
         - name: web
-          image: ghcr.io/example/admin-panel
+          image: ghcr.io/example/admin-panel:v1.0.0
           ports:
             - containerPort: 8080
+          securityContext:
+            runAsNonRoot: true
+            runAsUser: 1000
+            allowPrivilegeEscalation: false
+            readOnlyRootFilesystem: true
+          resources:
+            limits:
+              cpu: 500m
+              memory: 256Mi
+            requests:
+              cpu: 250m
+              memory: 128Mi
 ---
 apiVersion: v1
 kind: Service
@@ -27,9 +40,9 @@
   name: admin-panel
   namespace: internal
 spec:
-  type: LoadBalancer
+  type: ClusterIP
   selector:
     app: admin-panel
   ports:
     - port: 80
-      targetPort: 8080
+      targetPort: 8080
```
