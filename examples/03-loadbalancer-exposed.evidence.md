# BlastGuard AI evidence report

- Source: `03-loadbalancer-exposed.yaml`
- Model: `nvidia/nemotron-3-super-120b-a12b`
- Status: **BLOCKED -> VERIFIED**
- Attempts: 1  |  Wall time: 3.98s  |  Tokens: 1582 (prompt 1083, completion 499)

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
- Channel: tool_call  |  LLM latency: 3.77s  |  tokens: 1582
- Verification: PASS
- Remaining blocking findings: 0
- kubeconform: pass
- kube-linter: pass
- Model rationale:

> Fixed hostNetwork, automountServiceAccountToken, added securityContext (runAsNonRoot, non-zero runAsUser, allowPrivilegeEscalation false, readOnlyRootFilesystem), added CPU/memory limits/requests, pinned image tag, changed Service type to ClusterIP.

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
+              cpu: "100m"
+              memory: "128Mi"
+            requests:
+              cpu: "50m"
+              memory: "64Mi"
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
