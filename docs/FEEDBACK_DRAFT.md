# Feedback: Nebius Token Factory and NVIDIA Nemotron

First-hand notes from building BlastGuard AI. Every number comes from the saved runs in this repository
(`benchmark/results/`, `benchmark/blind/results/`, `runtime/collector.evidence.json`).

## Nebius Token Factory

What worked well
* OpenAI compatibility is real: the stock `openai` Python SDK worked with only `base_url` and the API key changed.
* `GET /v1/models` made picking `nvidia/nemotron-3-super-120b-a12b` trivial.
* Reliability under a test load: across the 48 benchmark runs plus 18 blind runs (about 90 model calls, 151k tokens
  in total) we saw 0 API errors and 0 harness errors. Median wall time per remediation run was about 5.4 s
  (maximum 15.2 s), including up to three model attempts.
* Tool calling worked: patches come back through a `submit_patch` function call (channel `tool_call` in the recorded
  evidence), so no free-text parsing was needed.
* Cost is easy to reason about: a typical run is about 1.5k to 3k tokens.

What could be better
* Key creation and model pages sat behind a billing-details form that needs a saved card (a $0.00 verification), even
  when you only want to use promo credits. It was not obvious up front. A short note on the sign-up page would save
  new users a detour.
* The billing address field rejected a German letter ("ö", "Use only Latin letters and numbers"), which is awkward
  for European users.
* There is no per-key spend limit that we could find in the console. We had to enforce our own caps in the app
  (per-session and process-wide run limits) to protect a public demo. A per-key budget would make public demos safer.
* The promo credit was applied under Billing, Payments, "With promo code"; this was easy to miss.

## NVIDIA Nemotron (nemotron-3-super-120b-a12b)

What worked well
* Instruction following on a structured task: it returned a complete patched manifest each time, kept the workload
  identity (name, kind, container names) and followed the verifier feedback on retry. In the recorded runs the retry
  loop fixed things like unset CPU requests flagged by kube-linter after the first attempt.
* It ignored prompt injection placed inside manifests in 3 of 3 runs on our corpus.
* Rationales were short and mostly accurate.

What we learned the hard way
* The model optimises for "the findings go away". On 5 function-critical cases (a log collector that needs a
  `hostPath`, a `hostNetwork` exporter, a public `LoadBalancer`, an eBPF agent needing `NET_ADMIN`, a `docker.sock`
  consumer) it removed the needed capability in every run that finished. 14 of those 35 verified patches pass every
  security check and break the workload. In a real Kubernetes cluster, the saved patch for our synthetic collector
  stopped collecting.
* In the blind suite the model sometimes invented details: `:latest` replaced by tags such as `v1.2.3` that may not
  exist, or a service-account token mounted without `ca.crt`. See `audit/AUDIT.md` for what we could confirm.
* Suggestion: a mode or system-prompt pattern for "minimal, behaviour-preserving diff, and say explicitly what
  you could not preserve" would be useful for infrastructure agents.

All numbers are on our own corpus (16 + 6 hand-written cases, one author, static oracles for most of them).
