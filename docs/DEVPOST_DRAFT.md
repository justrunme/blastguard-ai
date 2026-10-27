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
[PLACEHOLDER: fill from examples/summary.json after the first real run, worded "on this corpus".]

## Challenges
[PLACEHOLDER: fill with real issues hit during real runs, e.g. tool-call format, token budget, specific failures.]
* Designing the guard so "delete the workload" or "swap the image" can't count as a fix.

## What's next
* Wire in the original BlastGuard engine for CVE/exposure decisions on the images.
* Helm/Kustomize rendering, GitHub PR mode, admission-webhook dry-run mode.
* Larger evaluation corpus.

## Built with
Python, Streamlit, PyYAML, openai SDK, NVIDIA Nemotron, Nebius Token Factory, kubeconform, kube-linter.
