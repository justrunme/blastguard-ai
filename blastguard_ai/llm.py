"""NVIDIA Nemotron via Nebius Token Factory (OpenAI-compatible API).

The model only returns text (a proposed YAML manifest). That text is parsed as data,
never executed.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"

SYSTEM_PROMPT = """You are a Kubernetes security remediation engineer.
You receive a Kubernetes manifest and a list of findings from deterministic security checks.
Return a corrected version of the FULL manifest that resolves every blocking finding.

Hard constraints (a deterministic guard rejects violations):
- Keep every object: same kind, metadata.name and namespace. Do not delete or rename anything.
- Keep every container (same name) and the same image repository. You may change only the tag
  (pin a specific version instead of latest / no tag).
- Do not scale replicas to 0.
- You may add a NetworkPolicy object. Do not add other kinds of objects.
- Prefer minimal, production-sensible changes: securityContext (runAsNonRoot: true, a non-zero
  runAsUser, allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities drop ALL),
  resource requests/limits, replace hostPath with emptyDir, hostNetwork/hostPID/hostIPC false,
  automountServiceAccountToken: false, Service type ClusterIP instead of LoadBalancer.
- Output must be valid YAML for Kubernetes (multiple objects separated by ---).

Call the tool submit_patch exactly once with the full patched manifest."""

PATCH_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_patch",
        "description": "Submit the full patched Kubernetes manifest.",
        "parameters": {
            "type": "object",
            "properties": {
                "patched_yaml": {"type": "string", "description": "Complete patched manifest YAML"},
                "rationale": {"type": "string", "description": "Short list of changes made"},
            },
            "required": ["patched_yaml", "rationale"],
        },
    },
}


class LLMError(RuntimeError):
    """API/transport failure. The loop treats it as UNRESOLVED."""


@dataclass
class Proposal:
    patched_yaml: str | None
    rationale: str
    model: str
    latency_s: float
    usage: dict = field(default_factory=dict)
    channel: str = ""  # tool_call | content_fallback | none


@dataclass
class LLMConfig:
    base_url: str = field(default_factory=lambda: os.environ.get("NEBIUS_BASE_URL", DEFAULT_BASE_URL))
    model: str = field(default_factory=lambda: os.environ.get("NEBIUS_MODEL", DEFAULT_MODEL))
    max_tokens: int = field(default_factory=lambda: int(os.environ.get("BLASTGUARD_MAX_TOKENS", "8192")))
    timeout_s: float = field(default_factory=lambda: float(os.environ.get("BLASTGUARD_TIMEOUT_S", "90")))
    temperature: float = 0.2


def build_user_prompt(manifest: str, findings: list[dict], feedback: list[str]) -> str:
    parts = ["## Manifest\n```yaml\n" + manifest.strip() + "\n```",
             "## Blocking findings\n" + "\n".join(
                 f"- [{f['rule_id']}/{f['severity']}] {f['object']} container={f['container']}: {f['message']}"
                 for f in findings)]
    if feedback:
        parts.append("## Your previous attempt was rejected by the verifier\n" + "\n".join(f"- {x}" for x in feedback)
                     + "\nFix these issues in the new full manifest.")
    return "\n\n".join(parts)


_YAML_BLOCK = re.compile(r"```(?:ya?ml)?\s*\n(.*?)```", re.S)


def extract_from_content(content: str | None) -> str | None:
    if not content:
        return None
    m = _YAML_BLOCK.findall(content)
    return max(m, key=len) if m else None


class NebiusClient:
    """Real client. Requires NEBIUS_API_KEY in the environment; the key is never logged."""

    def __init__(self, config: LLMConfig | None = None):
        from openai import OpenAI

        self.config = config or LLMConfig()
        key = os.environ.get("NEBIUS_API_KEY")
        if not key:
            raise LLMError("NEBIUS_API_KEY is not set")
        self._client = OpenAI(base_url=self.config.base_url, api_key=key,
                              timeout=self.config.timeout_s, max_retries=1)

    @property
    def model(self) -> str:
        return self.config.model

    def list_models(self) -> list[str]:
        return sorted(m.id for m in self._client.models.list().data)

    def propose(self, manifest: str, findings: list[dict], feedback: list[str]) -> Proposal:
        t0 = time.monotonic()
        try:
            resp = self._client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": build_user_prompt(manifest, findings, feedback)}],
                tools=[PATCH_TOOL],
                tool_choice="auto",
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
        except Exception as exc:  # network, auth, rate limit, timeout
            raise LLMError(f"{exc.__class__.__name__}: {str(exc)[:200]}") from exc
        latency = time.monotonic() - t0
        usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
        if not resp.choices:
            return Proposal(None, "empty response", self.config.model, latency, usage, "none")
        msg = resp.choices[0].message
        for call in msg.tool_calls or []:
            if call.function.name == "submit_patch":
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    return Proposal(None, "tool arguments were not valid JSON", self.config.model, latency, usage,
                                    "tool_call")
                y = args.get("patched_yaml")
                return Proposal(y if isinstance(y, str) else None, str(args.get("rationale", ""))[:2000],
                                self.config.model, latency, usage, "tool_call")
        y = extract_from_content(msg.content)
        return Proposal(y, (msg.content or "")[:2000] if not y else "returned YAML in message content",
                        self.config.model, latency, usage, "content_fallback" if y else "none")
