# BlastGuard AI evidence report

- Source: `01-privileged-hostpath.yaml`
- Model: `nvidia/nemotron-3-super-120b-a12b`
- Status: **BLOCKED -> VERIFIED**
- Attempts: 1  |  Wall time: 3.74s  |  Tokens: 1635 (prompt 1148, completion 487)
- Release decision: **REVIEW_REQUIRED**

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
- Channel: tool_call  |  LLM latency: 3.56s  |  tokens: 1635
- Verification: PASS
- Remaining blocking findings: 0
- kubeconform: pass
- kube-linter: pass
- Model rationale:

> Replaced hostPath with emptyDir, disabled hostPID, removed privileged flag, dropped SYS_ADMIN capability, set runAsNonRoot true with non-zero UID, set allowPrivilegeEscalation false, readOnlyRootFilesystem true, added automountServiceAccountToken false, added CPU/memory requests and limits.

## Intent Preservation Gate

Verdict: **REVIEW_REQUIRED**. A security-clean patch changed what the workload does. Review before proposing.

| Severity | Code | Object | What changed |
|---|---|---|---|
| high | HOSTPATH_REPLACED | DaemonSet/observability/log-collector | hostPath volume 'host-root' (/) was replaced by emptyDir: the workload no longer sees the host files it was mounted to read or write |
| medium | HOSTPID_REMOVED | DaemonSet/observability/log-collector | hostPID was turned off: the workload no longer sees host processes/IPC |
| medium | SA_TOKEN_DISABLED | DaemonSet/observability/log-collector | service account token is no longer mounted: breaks the app if it calls the Kubernetes API |
| high | PRIVILEGED_REMOVED | DaemonSet/observability/log-collector container 'collector' | privileged mode was removed: anything needing device or kernel access will fail |
| medium | CAPABILITIES_REMOVED | DaemonSet/observability/log-collector container 'collector' | capabilities no longer added: ['SYS_ADMIN'] |
| medium | USER_CHANGED | DaemonSet/observability/log-collector container 'collector' | now runs as non-root (runAsUser 1000): the image must support that user |
| info | LIMITS_ADDED | DaemonSet/observability/log-collector container 'collector' | resource limits added: too-low values cause OOMKills or CPU throttling |

## Verified diff

```diff
--- original.yaml
+++ patched.yaml
@@ -1,4 +1,3 @@
-# Node agent that mounts the host filesystem and runs privileged.
 apiVersion: apps/v1
 kind: DaemonSet
 metadata:
@@ -13,18 +12,29 @@
       labels:
         app: log-collector
     spec:
-      hostPID: true
+      hostPID: false
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
+            requests:
+              cpu: "100m"
+              memory: "128Mi"
+            limits:
+              cpu: "200m"
+              memory: "256Mi"
       volumes:
         - name: host-root
-          hostPath:
-            path: /
+          emptyDir: {}
```
