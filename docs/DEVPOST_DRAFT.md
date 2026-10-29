# Devpost draft (do not submit without owner approval)

**Name:** BlastGuard AI: AI that can refuse, with proof
**Tagline:** Because a secure patch can still break production.
**Track:** Coding and Agentic Engineering

## Try it in 2 minutes
1. Open the [live demo](https://blastguard-ai.streamlit.app/), pick `01-privileged-hostpath`, press "Run remediation loop" (real Nemotron call, about 5 to 10 seconds).
2. Read the four-part strip: policy checks, external validators, intent preservation, release decision (REVIEW_REQUIRED). Open the Diff and Intent gate tabs.
3. Pick `04-stateless-api-missing-limits`: it needs two attempts (kube-linter fails the first) and ends SAFE_TO_PROPOSE.
4. See the evidence: [runtime proof in a real kind cluster](https://github.com/justrunme/blastguard-ai/actions/runs/40815098070), [benchmark A/B](https://github.com/justrunme/blastguard-ai/blob/main/benchmark/results/AB.md), [post-hoc audit](https://github.com/justrunme/blastguard-ai/blob/main/audit/AUDIT.md).

## What it is
An agent loop for Kubernetes security remediation. It finds misconfigurations with deterministic rules and external
validators, asks NVIDIA Nemotron (through Nebius Token Factory) for a patch, re-verifies the patch from scratch with
retries, and then runs an Intent Preservation Gate that decides whether the patch is safe to propose or needs a
human, because it changed what the workload does.

## The problem
Scanners tell you what is wrong. AI fixers make the findings disappear. But a patch can pass every security check
and still break the workload: a log collector loses its `hostPath`, an exporter loses `hostNetwork`, a service loses
its exposure. "Findings: 0" is not the same as "still works".

## How it works
1. Fail-closed YAML parsing (safe loader, size and document caps). Manifests are never executed.
2. 13 rules (BG001 to BG013), kubeconform schema validation and kube-linter.
3. Nemotron returns the full patched YAML through a `submit_patch` tool call. The patch goes into a sandbox,
   an identity guard blocks "fixes" that delete or swap the workload, and everything is re-checked.
4. Verifier feedback goes back to the model: up to 3 attempts.
5. The Intent Preservation Gate lists every drift (hostPath replaced, privileged removed, exposure changed, read-only
   root without a writable path, image tag changed, and more). High-impact drift means REVIEW_REQUIRED. If a
   validator is missing or the gate cannot decide, it fails closed to REVIEW_REQUIRED.
6. Evidence report (JSON and Markdown) per run: attempts, findings, tokens, timings, release decision.

## Evidence (all on our own corpus, nothing hidden)
* **Demo samples (real Nemotron runs):** 01, 02 and 03 pass security verification and are sent to review; 04 reaches SAFE_TO_PROPOSE after a real retry.
* **Benchmark, 16 cases, 48 real runs:** 35 patches passed security verification. A security-only tool would accept all 35, and 14 of them break the function the workload needs (for example `hostPath` turned into `emptyDir`). BlastGuard accepted 0 of those 14 as safe and sent them to review; it sent 0 function-preserving patches to review. Already-clean manifests (6 of 6) need no change, invalid inputs (6 of 6) are rejected before any model call, and a prompt injection inside a manifest was ignored in 3 of 3 runs. Static oracles, small corpus, written by the project.
* **Runtime proof (real kind cluster, GitHub Actions):** a synthetic collector reads a marker file from a node `hostPath`. The original reports COLLECTED; Nemotron's patch passes every security check and reports NOTHING_TO_COLLECT. The recorded run shows the real loop: attempt 1 failed (kept the hostPath), attempt 2 passed security, and the gate returned REVIEW_REQUIRED.
* **Blind challenge, 6 unseen cases, 18 real runs:** the frozen oracles found no broken function (0 false SAFE), and the gate sent 13 of 18 to review. We audited those calls afterwards in kind: 6 are confirmed breaks (nginx crash-loops on a read-only root; a kubectl CronJob fails TLS verification without `ca.crt`), 3 could not be tested, and 4 look like false alarms. So the oracles were too lax; the gate is strict but its reasons are generic. We publish this as is.

## What we are not claiming
VERIFIED means "passed these checks", not "works in your cluster". The app never touches a cluster. Corpora are small and
hand-written by one author; oracles are static and conceptually overlap the gate; the runtime proof is one synthetic case.

## Challenges
* Treating the model output as untrusted: any parse, API, budget or validator problem fails closed.
* A public demo needs a spend cap: per-session (10) and process-wide (1500) run limits.
* Validators missing on the hosted app: it now installs pinned kubeconform and kube-linter at start-up and records each validator's real status.
* Our own oracles turned out too weak on the blind suite, so we ran a cluster audit instead of tuning the gate to the answer.

## What existed before / what is new
The original [BlastGuard](https://github.com/justrunme/blastguard) (Go, a CVE blast-radius engine) existed before the Submission Period and is not integrated here. Everything in [blastguard-ai](https://github.com/justrunme/blastguard-ai) was built during the Submission Period: loop, rules, identity guard, Intent Preservation Gate, validator integration, Nemotron client, evidence reports, Streamlit UI, benchmark, blind suite, runtime proof and audit.

## What's next
Behaviour-preserving prompts and a minimal-diff mode, named failure reasons from the gate (for example "nginx needs a writable /tmp"), Helm and Kustomize rendering, a GitHub PR mode and an admission-webhook dry-run mode.

## Built with
Python, Streamlit, PyYAML, openai SDK, NVIDIA Nemotron (`nemotron-3-super-120b-a12b`), Nebius Token Factory, kubeconform, kube-linter, GitHub Actions, kind.
