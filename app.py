"""BlastGuard AI - Streamlit UI. Uses the real Nebius Token Factory API (no simulated model output)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import streamlit as st

from blastguard_ai.checks import RULES
from blastguard_ai.llm import LLMConfig, LLMError, NebiusClient
from blastguard_ai.loop import MAX_ATTEMPTS, run_remediation
from blastguard_ai.manifest import MAX_MANIFEST_BYTES
from blastguard_ai.report import to_json, to_markdown

SESSION_RUN_CAP = int(os.environ.get("BLASTGUARD_SESSION_RUN_CAP", "10"))
GLOBAL_RUN_CAP = int(os.environ.get("BLASTGUARD_GLOBAL_RUN_CAP", "1500"))
SAMPLES = {p.stem: p.read_text() for p in sorted((Path(__file__).parent / "samples").glob("*.yaml"))}
COLORS = {"BLOCKED": "#e5484d", "VERIFIED": "#30a46c", "UNRESOLVED": "#f5a524",
          "SAFE_TO_PROPOSE": "#30a46c", "NO_CHANGE_NEEDED": "#30a46c", "REVIEW_REQUIRED": "#f5a524", "NOT_PROPOSED": "#e5484d"}
RELEASE_TEXT = {
    "NO_CHANGE_NEEDED": "The manifest already passes every policy check and external validator. No patch was needed.",
    "SAFE_TO_PROPOSE": "Security verified and no high-impact static drift detected. Cluster behaviour is still not proven.",
    "REVIEW_REQUIRED": "Security passed, but the patch changes what the workload does. A human must review before it ships.",
    "NOT_PROPOSED": "No patch passed verification, so nothing is proposed.",
    "BLOCKED": "Findings remain and no remediation was run.",
}
SEV = {"critical": "🟥", "high": "🟧", "medium": "🟨", "info": "🟦"}

st.set_page_config(page_title="BlastGuard AI", page_icon="🛡️", layout="wide")
st.markdown("""<style>
.bg-hero h1{font-size:2.3rem;margin-bottom:0}
.bg-hero p{color:#8b949e;margin-top:.2rem}
.bg-badge{display:inline-block;padding:.35rem .9rem;border-radius:999px;color:#fff;font-weight:700;
 letter-spacing:.06em;font-size:1.05rem}
.bg-arrow{font-size:1.4rem;margin:0 .6rem;color:#8b949e}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def _global_counter() -> dict:
    return {"runs": 0}


@st.cache_resource(show_spinner="Installing optional validators (kubeconform, kube-linter)...")
def _ensure_validators() -> bool:
    """On hosts without the validator binaries (e.g. Streamlit Cloud), fetch the pinned releases once."""
    root = Path(__file__).parent
    if (root / "bin" / "kubeconform").exists() and (root / "bin" / "kube-linter").exists():
        return True
    try:
        subprocess.run(["sh", str(root / "scripts" / "install_tools.sh")], check=True, timeout=90,
                       capture_output=True)
        return True
    except Exception:
        return False


_ensure_validators()


def badge(status: str) -> str:
    return f'<span class="bg-badge" style="background:{COLORS.get(status, "#666")}">{status}</span>'


st.markdown('<div class="bg-hero"><h1>🛡️ BlastGuard AI</h1><p>Autonomous Kubernetes security remediation: '
            'deterministic checks find the risk, NVIDIA Nemotron proposes the fix, independent verifiers '
            'decide whether it ships. An intent gate flags patches that are secure but change what the app does.</p></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Run settings")
    cfg = LLMConfig()
    st.text_input("Model", cfg.model, disabled=True, help="Set NEBIUS_MODEL to change")
    st.caption(f"Endpoint: `{cfg.base_url}`")
    attempts = st.slider("Max attempts", 1, MAX_ATTEMPTS, MAX_ATTEMPTS)
    has_key = bool(os.environ.get("NEBIUS_API_KEY"))
    st.markdown("API key: " + ("✅ configured" if has_key else "❌ `NEBIUS_API_KEY` not set"))
    used = st.session_state.get("runs", 0)
    st.progress(min(used / SESSION_RUN_CAP, 1.0), text=f"Session runs: {used}/{SESSION_RUN_CAP}")
    st.caption(f"Limits: {MAX_ATTEMPTS} attempts, {cfg.max_tokens} max tokens/call, {int(cfg.timeout_s)}s "
               f"request timeout, {MAX_MANIFEST_BYTES // 1024} KB manifest cap. YAML only: no cluster access, "
               "nothing from the model is executed.")
    with st.expander("Rule set"):
        for rid, (sev, title) in RULES.items():
            st.markdown(f"{SEV[sev]} **{rid}** {title}")

left, right = st.columns([1, 1])
with left:
    choice = st.selectbox("Sample manifest", ["(paste your own)"] + list(SAMPLES))
    text = st.text_area("Manifest YAML", SAMPLES.get(choice, ""), height=380, key=f"ta-{choice}")
    go = st.button("🚀 Run remediation loop", type="primary", use_container_width=True,
                   disabled=not has_key or used >= SESSION_RUN_CAP)
    if not has_key:
        st.info("Set `NEBIUS_API_KEY` to run the real Nemotron loop.")

with right:
    st.subheader("Live step log")
    log_box = st.empty()

if go and _global_counter()["runs"] >= GLOBAL_RUN_CAP:
    st.error("The public demo has reached its overall run limit to protect the API budget. "
             "Clone the repo and run it with your own key.")
    go = False
if go:
    _global_counter()["runs"] += 1
    st.session_state["runs"] = used + 1
    lines: list[str] = []

    def on_event(msg: str) -> None:
        lines.append(msg)
        log_box.code("\n".join(lines), language="text")

    try:
        client = NebiusClient(cfg)
    except LLMError as exc:
        st.error(str(exc))
        st.stop()
    with st.spinner("Running detect → patch → verify loop…"):
        st.session_state["result"] = run_remediation(text, client, max_attempts=attempts, on_event=on_event)
        st.session_state["source"] = choice
    st.rerun()

res = st.session_state.get("result")
if res:
    if not go:
        log_box.code("\n".join(res.events), language="text")
    st.divider()
    t = res.totals()
    st.markdown(f'{badge(res.initial_status)}<span class="bg-arrow">→</span>{badge(res.status)}',
                unsafe_allow_html=True)
    last = res.attempts[-1].get("verification", {}) if res.attempts else {}
    rem_blocking = len([f for f in last.get("findings", []) if f["blocking"]]) if last else None
    vals = last.get("validators", []) if last else []
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown("**1. Policy checks**")
    c1.markdown(f"{len([f for f in res.initial_findings if f['blocking']])} blocking → "
                f"{rem_blocking if rem_blocking is not None else '–'} remaining")
    c2.markdown("**2. External validators**")
    c2.markdown("<br>".join(f"{v['name']}: **{v['status']}**" for v in vals) or "not run")
    if res.status == "VERIFIED" and not res.validators_complete:
        c2.caption("Incomplete: not counted as independent verification.")
    c3.markdown("**3. Intent preservation**")
    if res.intent is None:
        c3.markdown("not run")
    else:
        hi = len([d for d in res.intent["drifts"] if d["severity"] == "high"])
        c3.markdown(f"**{res.intent['verdict']}**<br>{hi} high-impact, {len(res.intent['drifts'])} total drifts",
                    unsafe_allow_html=True)
    c4.markdown("**4. Release decision**")
    c4.markdown(badge(res.release), unsafe_allow_html=True)
    st.caption(res.release_note or RELEASE_TEXT[res.release])
    m = st.columns(5)
    m[0].metric("Initial findings", len([f for f in res.initial_findings if f["blocking"]]))
    m[1].metric("Remaining", len([f for f in last.get("findings", []) if f["blocking"]]) if last else "–")
    m[2].metric("Attempts", len(res.attempts))
    m[3].metric("Tokens", t["total_tokens"])
    m[4].metric("Wall time", f"{res.wall_s}s")
    if res.error:
        st.warning(res.error)

    tabs = st.tabs(["Findings", "Diff", "Intent gate", "Attempts", "Evidence report"])
    with tabs[0]:
        st.dataframe([{"": SEV[f["severity"]], **{k: f[k] for k in ("rule_id", "severity", "object", "container",
                                                                    "message")}} for f in res.initial_findings],
                     use_container_width=True, hide_index=True)
        st.caption("Validators on input: " + (", ".join(f"{v['name']}={v['status']}"
                                                         for v in res.validators_initial) or "none"))
    with tabs[1]:
        shown = res.final_yaml if res.status == "VERIFIED" else res.last_candidate
        if shown:
            if res.status != "VERIFIED":
                st.warning("Last candidate did NOT pass verification. Shown for review only.")
            a, b = st.columns(2)
            a.markdown("**Original**")
            a.code(res.original_yaml, language="yaml")
            b.markdown("**Patched**" + (" ✅ verified" if res.status == "VERIFIED" else " ⚠️ unverified"))
            b.code(shown, language="yaml")
            if res.diff:
                st.code(res.diff, language="diff")
        else:
            st.info("No patch to show.")
    with tabs[2]:
        if res.intent is None:
            st.info("The Intent Preservation Gate runs on a patch that passed security verification.")
        else:
            (st.warning if res.intent["verdict"] == "REVIEW_REQUIRED" else st.success)(
                f"{res.intent['verdict']}: {res.intent['note']}")
            if res.intent["drifts"]:
                st.dataframe(res.intent["drifts"], use_container_width=True, hide_index=True)
    with tabs[3]:
        for at in res.attempts:
            v = at.get("verification", {})
            ok = v.get("ok")
            with st.expander(f"Attempt {at['attempt']}: {'PASS' if ok else 'FAIL'}", expanded=not ok):
                if at.get("error"):
                    st.error(at["error"])
                    continue
                st.write(f"Channel `{at.get('channel')}` · latency {at.get('llm_latency_s')}s · "
                         f"tokens {(at.get('usage') or {}).get('total_tokens')}")
                if v.get("parse_error"):
                    st.error(v["parse_error"])
                for g in v.get("guard", []):
                    st.error(f"Identity guard: {g}")
                for val in v.get("validators", []):
                    st.write(f"**{val['name']}**: {val['status']}")
                    for i in val["issues"][:10]:
                        st.caption(i)
                rem = [f for f in v.get("findings", []) if f["blocking"]]
                if rem:
                    st.dataframe(rem, hide_index=True)
                if at.get("rationale"):
                    st.markdown("**Model rationale**")
                    st.text(at["rationale"])
    with tabs[4]:
        src = st.session_state.get("source", "input")
        md = to_markdown(res, src)
        c1, c2 = st.columns(2)
        c1.download_button("⬇️ Evidence JSON", to_json(res, src), f"blastguard-{src}.json", "application/json",
                           use_container_width=True)
        c2.download_button("⬇️ Evidence Markdown", md, f"blastguard-{src}.md", "text/markdown",
                           use_container_width=True)
        st.markdown(md)
