"""Run the real Nemotron loop on every sample and save evidence to examples/.

Requires NEBIUS_API_KEY. The key is read from the environment and never printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from blastguard_ai.llm import LLMError, NebiusClient  # noqa: E402
from blastguard_ai.loop import run_remediation  # noqa: E402
from blastguard_ai.report import to_json, to_markdown  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "examples"))
    ap.add_argument("samples", nargs="*")
    args = ap.parse_args()
    try:
        client = NebiusClient()
    except LLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.list_models:
        print("\n".join(client.list_models()))
        return 0
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    paths = [Path(p) for p in args.samples] or sorted((ROOT / "samples").glob("*.yaml"))
    summary = []
    for p in paths:
        print(f"== {p.name}", flush=True)
        res = run_remediation(p.read_text(), client, on_event=lambda m: print("  " + m, flush=True))
        (out / f"{p.stem}.evidence.json").write_text(to_json(res, p.name))
        (out / f"{p.stem}.evidence.md").write_text(to_markdown(res, p.name))
        summary.append({"sample": p.name, "initial": res.initial_status, "final": res.status,
                        "attempts": len(res.attempts), "release": res.release, "error": res.error, **res.totals(), "wall_s": res.wall_s})
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
