"""TEST-ONLY fake LLM clients. Never used by the app; outputs here are scripted, not model outputs."""
from blastguard_ai.llm import LLMError, Proposal


class ScriptedFakeClient:
    model = "TEST-FAKE-scripted"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def propose(self, manifest, findings, feedback):
        self.calls.append({"manifest": manifest, "findings": findings, "feedback": feedback})
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return Proposal(out, "scripted test output", self.model, 0.01,
                        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, "tool_call")


class ErrorFakeClient(ScriptedFakeClient):
    def __init__(self):
        super().__init__([LLMError("APIConnectionError: simulated in test")] * 3)
