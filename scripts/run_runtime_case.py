"""Run the real BlastGuard loop on runtime/collector.yaml and save the patched manifest + evidence."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from blastguard_ai.llm import NebiusClient
from blastguard_ai.loop import run_remediation
from blastguard_ai.report import to_json

root = Path(__file__).resolve().parent.parent
src = (root / "runtime/collector.yaml").read_text()
res = run_remediation(src, NebiusClient())
print("status", res.status, "release", res.release, "attempts", len(res.attempts))
(root / "runtime/collector.evidence.json").write_text(to_json(res, "runtime/collector.yaml"))
if res.final_yaml:
    (root / "runtime/collector.patched.yaml").write_text(res.final_yaml)
