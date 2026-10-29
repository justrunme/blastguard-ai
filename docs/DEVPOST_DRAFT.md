# Devpost draft (do not submit without owner approval)

**Name:** BlastGuard AI: Autonomous Kubernetes Security Remediation Agent
**Track:** Coding and Agentic Engineering

## What it is
A web app that takes a Kubernetes manifest, finds security misconfigurations with deterministic rules, asks NVIDIA
Nemotron (via Nebius Token Factory) for a patch, and accepts the patch only if independent verifiers pass:
BLOCKED → VERIFIED, or UNRESOLVED with evidence of why.

## Why we built it
Misconfigured manifests (privileged pods, hostPath, root, LoadBalancer exposure) are common and their fixes are
routine but tedious. LLMs can write those fixes, but an unchecked LLM fix is a new risk. We wanted an agent loop
where the model does the work and deterministic tools hold the veto.

## How it works
1. Fail-closed YAML parsing (size cap, safe loader).
2. 13 Python rules (BG001-BG013) + kubeconform schema validation + kube-linter security subset.
3. Nemotron receives the manifest and findings and returns the full patched YAML through a `submit_patch` tool call.
4. The candidate is written to a temp sandbox (never executed), re-checked, and an identity guard ensures the
   workload was fixed, not deleted or swapped.
5. Up to 3 attempts with verifier feedback; evidence report (JSON/Markdown) with per-attempt findings, tokens, timings.

## Results
On this corpus (3 intentionally dangerous manifests; real Nemotron calls via Token Factory), all three went
BLOCKED → VERIFIED on the first attempt, in 2.9 to 4.8 seconds and 1,403 to 1,649 tokens per run. Blocking findings
before the patch: 9, 6 and 8; after the patch: 0, verified by the deterministic rules, kubeconform and kube-linter.
This is a smoke test on three samples, not an evaluation, and VERIFIED means "passed these checks", not "works in a
cluster": in sample 01 the model swapped `hostPath: /` for an `emptyDir`, which is safe but would break a real log
collector. The retry path was not needed by the real model on this corpus.

## Challenges
* Getting a verdict you can trust: the model's output is treated as untrusted input, so the loop fails closed to
  UNRESOLVED on any parse, API or budget problem.
* The first hosted run showed `kubeconform` and `kube-linter` as `not_installed` on Streamlit Cloud, so the app now
  fetches the pinned releases at start-up and the evidence report records each validator's real status.
* A public demo needs a spend cap: session and process-wide run limits protect the API budget.
* Designing the guard so "delete the workload" or "swap the image" can't count as a fix.

## What existed before / what is new
The original [BlastGuard](https://github.com/justrunme/blastguard) (Go, a CVE blast-radius decision engine) existed
before the Submission Period and is not integrated in this MVP. Everything in
[blastguard-ai](https://github.com/justrunme/blastguard-ai) was built during the Submission Period: remediation
loop, 13 rules, identity guard, validator integration, Nemotron client, evidence reports, Streamlit UI, tests.

## What's next
* Wire in the original BlastGuard engine for CVE/exposure decisions on the images.
* Helm/Kustomize rendering, GitHub PR mode, admission-webhook dry-run mode.
* Larger evaluation corpus.

## Built with
Python, Streamlit, PyYAML, openai SDK, NVIDIA Nemotron, Nebius Token Factory, kubeconform, kube-linter.
