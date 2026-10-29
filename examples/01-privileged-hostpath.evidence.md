# BlastGuard AI evidence report

- Source: `01-privileged-hostpath.yaml`
- Model: `nvidia/nemotron-3-super-120b-a12b`
- Status: **BLOCKED -> VERIFIED**
- Attempts: 1  |  Wall time: 4.82s  |  Tokens: 1649 (prompt 1148, completion 501)

## Initial findings

| Rule | Severity | Object | Container | Message |
|---|---|---|---|---|
| BG002 | critical | DaemonSet/observability/log-collector | - | hostPath volume mounted: volume 'host-root' -> / |
| BG004 | high | DaemonSet/observability/log-collector | - | hostPID / hostIPC enabled |
| BG011 | medium | DaemonSet/observability/log-collector | - | Service account token automounted: set automountServiceAccountToken: false unless the API is needed |
| BG001 | critical | DaemonSet/observability/log-collector | collector | Privileged container |
| BG005 | high | DaemonSet/observability/log-collector | collector | May run as root (runAsNonRoot not true or runAsUser 0) |
| BG006 | high | DaemonSet/observability/log-collector | collector | allowPrivilegeEscalation not explicitly false |
| BG007 | medium | DaemonSet/observability/log-collector | collector | Missing CPU/memory limits: missing cpu,memory |
| BG009 | medium | DaemonSet/observability/log-collector | collector | readOnlyRootFilesystem not true |
| BG010 | critical | DaemonSet/observability/log-collector | collector | Dangerous Linux capability added: SYS_ADMIN |
| BG013 | info | bundle | - | No NetworkPolicy in this manifest bundle: consider a default-deny NetworkPolicy |

Initial validators: kubeconform=pass, kube-linter=fail

## Attempt 1
- Channel: tool_call  |  LLM latency: 4.66s  |  tokens: 1649
- Verification: PASS
- Remaining blocking findings: 0
- kubeconform: pass
- kube-linter: pass
- Model rationale:

> Removed privileged, hostPID, hostPath replaced with emptyDir, set automountServiceAccountToken false, added securityContext with runAsNonRoot, non-zero user, no privilege escalation, readOnly rootfs, dropped all capabilities, added resource limits/requests.

## Verified diff

```diff
--- original.yaml
+++ patched.yaml
@@ -1,4 +1,3 @@
-# Node agent that mounts the host filesystem and runs privileged.
 apiVersion: apps/v1
 kind: DaemonSet
 metadata:
@@ -13,18 +12,28 @@
       labels:
         app: log-collector
     spec:
-      hostPID: true
+      automountServiceAccountToken: false
       containers:
         - name: collector
           image: fluent/fluent-bit:3.1.9
           securityContext:
-            privileged: true
+            privileged: false
+            runAsNonRoot: true
+            runAsUser: 1000
+            allowPrivilegeEscalation: false
+            readOnlyRootFilesystem: true
             capabilities:
-              add: ["SYS_ADMIN"]
+              drop: ["ALL"]
           volumeMounts:
             - name: host-root
               mountPath: /host
+          resources:
+            limits:
+              cpu: "500m"
+              memory: "256Mi"
+            requests:
+              cpu: "200m"
+              memory: "128Mi"
       volumes:
         - name: host-root
-          hostPath:
-            path: /
+          emptyDir: {}
```
