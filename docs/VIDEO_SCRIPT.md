# Demo video script (target 2:45, max 3:00)

No third-party music or logos beyond the required sponsor mentions in narration. Screen recording + voiceover.

| Time | Shot | Voiceover |
|---|---|---|
| 0:00-0:15 | Title card: "BlastGuard AI" on dark background | "Kubernetes scanners tell you what is wrong. BlastGuard AI fixes it, and proves the fix." |
| 0:15-0:35 | Sample 01 manifest in the UI, highlight `privileged`, `hostPath: /` | "This log collector runs privileged and mounts the whole node filesystem. One compromise, whole node." |
| 0:35-0:55 | Click Run; live step log; red BLOCKED badge, findings table | "Deterministic checks, no AI involved, find N blocking issues. kubeconform and kube-linter run too." |
| 0:55-1:30 | Attempt log: Nemotron call, tokens, latency; attempt PASS/FAIL expanders | "NVIDIA Nemotron on Nebius Token Factory proposes a full patched manifest through a tool call. It goes into a sandbox, never executed, and is re-checked from scratch. If anything still fails, the exact failures go back to the model. Max three attempts." |
| 1:30-1:55 | Badge BLOCKED → VERIFIED (use the real result; if UNRESOLVED, show that) | Read the real outcome as recorded. |
| 1:55-2:15 | Side-by-side diff | "Here is exactly what changed: non-root, no privilege escalation, emptyDir instead of hostPath, limits." |
| 2:15-2:30 | Try identity-guard story: attempt that deleted/renamed (only if it happened in a real run; otherwise skip) | "The model cannot cheat by deleting the workload: an identity guard checks names, containers and images." |
| 2:30-2:45 | Download evidence JSON/MD | "Every run produces an evidence report: findings per attempt, tokens, timings." |
| 2:45-3:00 | Architecture diagram from README, repo URL | "Model proposes, deterministic tools decide. BlastGuard AI." |

Recording notes: use only real runs; do not edit numbers on screen.
