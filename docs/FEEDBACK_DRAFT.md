# Feedback draft: Nebius Token Factory / AI Cloud / NVIDIA tools

Only first-hand experiences from building this project. Placeholders are marked and must be filled or removed.

## Token Factory
* OpenAI-compatible API: the stock `openai` Python SDK worked with only `base_url` changed. Confirmed: the stock `openai` SDK worked with only `base_url` and the API key set.
* Model discovery via `GET /v1/models` returned 200 with the five Nemotron models we expected plus many other families, which made it easy to pick a model ID.
* Tool calling with `nvidia/nemotron-3-super-120b-a12b`: the `submit_patch` function was called on every attempt (3 of 3 runs, channel `tool_call`); the plain-text fallback was never needed.
* Latency / token usage per call: 2.7 to 4.7 s LLM latency and 1,403 to 1,649 total tokens per remediation run on our three samples.
* Key creation: API keys and the model pages were blocked behind a billing-details form that needs a saved card (a $0.00 bank verification), even when you only want to use promo credits. It was not obvious up front, and the street field rejected the German letter "ö" ("Use only Latin letters and numbers").
* Credits: the promo code was applied under Billing → Payments → "+" → "With promo code"; the balance showed $29.75 after the Builder Program credit and the promo, more than the $25 we expected.

## Nebius AI Cloud
* Not used: the demo runs on Streamlit Community Cloud and calls Token Factory over the API.

## NVIDIA Nemotron
* Patch quality on the 3 samples: all three patches passed our deterministic rules, kubeconform and kube-linter on the first attempt. One patch was safe but functionally lossy (`hostPath: /` replaced with `emptyDir`), so a human must review the diff.
* Token use was small (about 1.4k to 1.6k tokens per run) and the rationale returned with each patch was concise and accurate.
