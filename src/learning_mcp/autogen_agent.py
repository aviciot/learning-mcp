# /src/learning_mcp/autogen_agent.py
"""
AutoGen planner (with critic) that pulls per-profile hints from learning.yaml
via /config/profile/{name}, builds templated system messages, and iterates
search → plan → critique up to MAX_LOOPS (default 3).

Key features:
- YAML-driven, but with a stable base template in code (templated system messages).
- Planner & Critic are separate AssistantAgent instances (same client).
- Two-pass JSON validation (generate → repair).
- Enriched outputs (confidence, evidence_used, missing_info, recommended_queries, etc.).

ENV:
  USE_AUTOGEN=1
  AUTOGEN_BACKEND=cloudflare | openai | ollama
  AUTOGEN_MODEL=@cf/meta/llama-3.1-8b-instruct
  OPENAI_API_KEY=...
  OPENAI_BASE_URL=...
  API_AGENT_BASE_URL=http://localhost:8013
  API_AGENT_SEARCH_TIMEOUT=90          # total client timeout (seconds)
  AUTOGEN_MAX_LOOPS=3
"""

from __future__ import annotations

import os
import re
import json
import logging
from typing import Any, Dict, Optional, Tuple, List

import httpx

log = logging.getLogger("autogen_agent")
log.setLevel(logging.INFO)

# Lazy imports so the server can still boot if autogen isn't installed.
try:
    from autogen_agentchat.agents import AssistantAgent
    from autogen_ext.models.openai import OpenAIChatCompletionClient
    from autogen_core.models import ModelInfo
except Exception as e:
    log.error("autogen.import.failed %s", e)
    AssistantAgent = None
    OpenAIChatCompletionClient = None
    ModelInfo = None

BASE_URL = os.getenv("API_AGENT_BASE_URL", "http://localhost:8013").rstrip("/")
BACKEND = os.getenv("AUTOGEN_BACKEND", "cloudflare")
MODEL = os.getenv("AUTOGEN_MODEL", "@cf/meta/llama-3.1-8b-instruct")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE = os.getenv("OPENAI_BASE_URL")

MAX_LOOPS = int(os.getenv("AUTOGEN_MAX_LOOPS", "3"))
SEARCH_TIMEOUT_S = float(os.getenv("API_AGENT_SEARCH_TIMEOUT", "90"))

_CODEFENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


# -----------------------
# Utility: JSON extraction
# -----------------------
def _extract_text_from_reply(reply: Any) -> Optional[str]:
    """Extract assistant text content from various AutoGen reply shapes."""
    c = getattr(reply, "content", None)
    if isinstance(c, str) and c.strip():
        return c.strip()
    msgs = getattr(reply, "messages", None)
    if msgs and isinstance(msgs, (list, tuple)):
        for m in reversed(msgs):
            mc = getattr(m, "content", None)
            if isinstance(mc, str) and mc.strip():
                return mc.strip()
    if isinstance(reply, (list, tuple)) and reply:
        for m in reversed(reply):
            mc = getattr(m, "content", None)
            if isinstance(mc, str) and mc.strip():
                return mc.strip()
    if isinstance(reply, dict):
        c = reply.get("content")
        if isinstance(c, str) and c.strip():
            return c.strip()
    s = str(reply).strip()
    return s or None


def _strip_code_fences(text: str) -> str:
    m = _CODEFENCE_RE.match(text.strip())
    return m.group(1).strip() if m else text.strip()


def _find_top_level_json(text: str) -> Optional[str]:
    """Find the first top-level {...} JSON object via brace balancing."""
    s = text.strip()
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _parse_json_strict(text: str) -> Tuple[Optional[dict], Optional[str]]:
    """Strict parse to JSON: strip fences, find top-level object, then json.loads."""
    raw = _strip_code_fences(text)
    candidate = _find_top_level_json(raw) or raw
    try:
        obj = json.loads(candidate)
        return obj, None
    except Exception as e:
        return None, f"{e}"


def _fmt_params(d: dict) -> str:
    try:
        return json.dumps(d, separators=(",", ":"))
    except Exception:
        return str(d)


# -----------------------
# Config / Hints loader
# -----------------------
async def _load_profile_hints(profile_name: str) -> dict:
    """
    Fetch autogen_hints for a profile via /config/profile/{name}.
    Returns {} on error/missing.
    """
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(f"{BASE_URL}/config/profile/{profile_name}")
            r.raise_for_status()
            data = r.json() or {}
            prof = data.get("profile") or {}
            hints = prof.get("autogen_hints") or {}
            return hints
    except Exception as e:
        log.warning("autogen.hints.load.failed profile=%s err=%s", profile_name, e)
        return {}


def _build_system_messages_from_hints(hints: dict) -> tuple[str, str]:
    """
    Build planner & critic system messages using a stable base template,
    enriched with minimal YAML hints (labels, endpoint pattern, templates, examples).
    """
    labels = hints.get("labels") or {}
    endpoint = hints.get("endpoint") or {}
    templates = hints.get("templates") or {}
    examples = hints.get("endpoint_examples") or []

    api_plan_label = labels.get("api_plan", "API PLAN critic")
    api_call_label = labels.get("api_call_plan", "API CALL PLAN")

    allow_pattern = endpoint.get("allow_pattern", "")
    forbid_patterns = endpoint.get("forbid_patterns") or []

    read_t = templates.get("read") or {}
    write_t = templates.get("write") or {}
    write_req_example = bool(write_t.get("require_example_in_evidence"))

    read_form = f"{read_t.get('method','GET')} params={_fmt_params(read_t.get('params') or {})}" if read_t else "GET params={}"
    write_form = f"{write_t.get('method','GET')} params={_fmt_params(write_t.get('params') or {})}" if write_t else "GET params={}"

    forbid_line = ", ".join(forbid_patterns) if forbid_patterns else "(none)"
    example_line = "\n- ".join(examples[:3]) if examples else ""

    planner_system_message = (
        f"You convert retriever evidence into an {api_call_label}.\n"
        "Output STRICT JSON ONLY with keys: endpoint (string), method (string), "
        "params (object), provenance (object with top_hit).\n"
        "Rules:\n"
        f"- Endpoint must match allowed pattern: {allow_pattern or '(none specified)'}\n"
        f"- Never output endpoints that match forbidden patterns: {forbid_line}\n"
        f"- Reads: follow this form: {read_form}\n"
        f"- Writes: follow this form: {write_form}"
        + (" (only if a concrete example appears in evidence)" if write_req_example else "")
        + ("\nExamples:\n- " + example_line if example_line else "")
    )

    critic_system_message = (
        f"You are a strict {api_plan_label}.\n"
        "Input: a candidate plan and the top evidence.\n"
        "Output STRICT JSON ONLY with keys: verdict ('pass'|'fail'), confidence (0..1), "
        "missing (array of strings), next_search (array of strings), risk_flags (array).\n"
        "Rules:\n"
        f"- Fail if endpoint does not match allowed pattern {allow_pattern or '(none)'} "
        f"or matches any forbidden pattern: {forbid_line}\n"
        "- If method modifies state (not pure read), require at least one concrete example in evidence.\n"
        "- Propose precise follow-up search queries when failing.\n"
        "- Prefer short, targeted queries (≤3 tokens; include exact param names if visible in evidence)."
    )
    return planner_system_message, critic_system_message


# -----------------------
# Evidence retrieval
# -----------------------
async def _search_once(q: str, profile: str, top_k: int = 8) -> List[dict]:
    payload = {"q": q, "profile": profile, "top_k": top_k, "read_only": True}
    timeout = httpx.Timeout(SEARCH_TIMEOUT_S)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{BASE_URL}/search/api_context", json=payload)
        r.raise_for_status()
        data = r.json()
    return data.get("results") or []


async def _fetch_evidence(q: str, profile: str | None) -> Tuple[list[dict], Optional[str]]:
    """
    Get evidence and return a small preview (top-3 with useful fields)
    for the planner prompt.
    """
    try:
        hits = await _search_once(q, profile or "default")
        preview = []
        for h in hits[:3]:
            hints = h.get("hints") or {}
            preview.append(
                {
                    "score": h.get("score"),
                    "snippet": h.get("snippet"),
                    "doc_path": h.get("doc_path"),
                    "chunk_idx": h.get("chunk_idx"),
                    "url_candidates": hints.get("url_candidates"),
                    "method_hint": hints.get("method_hint"),
                    "query_candidates": hints.get("query_candidates"),
                }
            )
        return preview, None
    except Exception as e:
        return [], f"retriever for autogen failed: {e}"


# -----------------------
# Client & Agents
# -----------------------
def _make_client() -> Tuple[Optional[OpenAIChatCompletionClient], Optional[str]]:
    """Initialize OpenAI-compatible client (CF/OpenAI/Ollama via /v1)."""
    try:
        client = OpenAIChatCompletionClient(
            model=MODEL,
            api_key=OPENAI_KEY,
            base_url=OPENAI_BASE,
            model_info=ModelInfo(
                vision=False,
                function_calling=False,  # manual “no tools” mode
                json_output=True,
                structured_output=False,
                family="unknown",
            ),
        )
        log.info("autogen.client.init base=%s backend=%s", OPENAI_BASE, BACKEND)
        return client, None
    except Exception as e:
        return None, f"Client init failed: {e}"


def _valid_endpoint(endpoint: str, allow_pattern: str, forbid_patterns: List[str]) -> bool:
    try:
        if allow_pattern and not re.search(allow_pattern, endpoint or ""):
            return False
        for fp in forbid_patterns or []:
            if re.search(fp, endpoint or ""):
                return False
        return True
    except Exception:
        return False


# -----------------------
# Main entry
# -----------------------
async def plan_with_autogen(q: str, profile: str | None = None) -> Dict[str, Any]:
    """
    Generate an API call plan using a planner+critic loop with YAML-driven
    system messages. Returns enriched payload on success or needs_input on failure.
    """
    log.info("autogen.v2.start q=%s profile=%s backend=%s model=%s", q, profile, BACKEND, MODEL)

    if AssistantAgent is None or OpenAIChatCompletionClient is None:
        return {"status": "needs_input", "reason": "AutoGen not installed"}

    # Load profile hints (safe if empty)
    hints = await _load_profile_hints(profile or "default")
    planner_msg, critic_msg = _build_system_messages_from_hints(hints)

    allow_pattern = (hints.get("endpoint") or {}).get("allow_pattern", "")
    forbid_patterns = (hints.get("endpoint") or {}).get("forbid_patterns") or []
    read_template = (hints.get("templates") or {}).get("read") or {}
    write_template = (hints.get("templates") or {}).get("write") or {}
    write_req_example = bool(write_template.get("require_example_in_evidence"))

    # Client & agents
    client, err = _make_client()
    if err:
        return {"status": "needs_input", "reason": err}

    try:
        planner = AssistantAgent(
            name="api_planner",
            model_client=client,
            system_message=planner_msg,
        )
        critic = AssistantAgent(
            name="api_critic",
            model_client=client,
            system_message=critic_msg,
        )
    except Exception as e:
        return {"status": "needs_input", "reason": f"Agent init failed: {e}"}

    # Loop state
    trace: List[dict] = []
    all_hits: List[dict] = []
    queries: List[str] = [q]

    for loop_idx in range(1, MAX_LOOPS + 1):
        log.info("autogen.loop.start idx=%s queries=%s", loop_idx, queries)

        # 1) Search (merge new hits)
        new_hits_all: List[dict] = []
        for qtext in queries:
            try:
                hits = await _search_once(qtext, profile or "default")
                new_hits_all.extend(hits)
            except Exception as e:
                log.warning("autogen.search.error q=%s err=%s", qtext, e)

        # If we found nothing new, keep working with what we have
        if not new_hits_all and not all_hits:
            return {"status": "needs_input", "reason": "Retriever returned no evidence."}

        if new_hits_all:
            all_hits.extend(new_hits_all)
            log.info("autogen.search.hit q=%s count=%s", queries[0], len(new_hits_all))

        # Top-3 preview for the planner
        preview = []
        for h in (new_hits_all or all_hits)[:3]:
            hints_h = h.get("hints") or {}
            preview.append(
                {
                    "score": h.get("score"),
                    "snippet": h.get("snippet"),
                    "doc_path": h.get("doc_path"),
                    "chunk_idx": h.get("chunk_idx"),
                    "url_candidates": hints_h.get("url_candidates"),
                    "method_hint": hints_h.get("method_hint"),
                    "query_candidates": hints_h.get("query_candidates"),
                }
            )

        # 2) Planner: first pass
        plan_task = (
            "Given the EVIDENCE below and the USER QUERY, produce STRICT JSON.\n"
            "Required keys: endpoint (string), method (string), params (object), provenance (object with top_hit).\n"
            "Do NOT include code fences or commentary—JSON only.\n"
            f"USER QUERY: {q}\n\n"
            f"EVIDENCE (top-3): {json.dumps(preview, ensure_ascii=False)}"
        )
        log.info("autogen.planner.prompt idx=%s prompt=%s", loop_idx, plan_task[:1024])
        try:
            plan_reply = await planner.run(task=plan_task)
            plan_text = _extract_text_from_reply(plan_reply) or ""
            candidate_plan, jerr = _parse_json_strict(plan_text)
            if not candidate_plan:
                # 3) Planner: repair pass
                repair_prompt = (
                    "The previous output was not valid JSON or missing required keys.\n"
                    "Repair it to STRICT, VALID, MINIFIED JSON ONLY. No code fences. No comments. No extra text.\n"
                    "Required keys: endpoint (string), method (string), params (object), provenance (object with top_hit).\n"
                    f"Here is your previous output:\n{plan_text}"
                )
                repair_reply = await planner.run(task=repair_prompt)
                plan_text = _extract_text_from_reply(repair_reply) or ""
                candidate_plan, _ = _parse_json_strict(plan_text)
        except Exception as e:
            return {"status": "needs_input", "reason": f"AutoGen failed to plan: {e}"}

        # If still no valid JSON, let critic suggest next searches (generic)
        if not candidate_plan or not isinstance(candidate_plan, dict):
            critic_task = (
                "Plan output is invalid or missing. "
                "Provide next_search (short keyword queries) and what's missing. JSON only."
            )
            log.info("autogen.critic.prompt idx=%s prompt=%s", loop_idx, critic_task)
            try:
                critic_reply = await critic.run(task=critic_task)
                ctext = _extract_text_from_reply(critic_reply) or ""
                cobj, _ = _parse_json_strict(ctext)
                missing = (cobj or {}).get("missing") or []
                next_search = (cobj or {}).get("next_search") or []
            except Exception:
                missing, next_search = ["valid JSON plan"], []
            trace.append(
                {"loop": loop_idx, "plan": plan_text, "critic": {"missing": missing, "next_search": next_search}, "evidence_top3": preview}
            )
            if loop_idx >= MAX_LOOPS:
                return _final_needs_input(all_hits, trace, missing)
            queries = next_search or queries  # if critic empty, retry same query
            continue

        # 4) Critic: evaluate candidate plan
        try:
            c_in = {
                "endpoint": candidate_plan.get("endpoint"),
                "method": candidate_plan.get("method"),
                "params": candidate_plan.get("params"),
                "provenance": candidate_plan.get("provenance"),
            }
            critic_prompt = (
                "Plan to evaluate (JSON):\n"
                f"{json.dumps(c_in, ensure_ascii=False)}\n"
                "Top evidence (minified):\n"
                f"{json.dumps(preview, ensure_ascii=False)}"
            )
            log.info("autogen.critic.prompt idx=%s prompt=%s", loop_idx, critic_prompt[:1024])
            critic_reply = await critic.run(task=critic_prompt)
            ctext = _extract_text_from_reply(critic_reply) or ""
            cobj, _ = _parse_json_strict(ctext)
        except Exception as e:
            cobj = {"verdict": "fail", "missing": [f"critic failed: {e}"], "next_search": []}

        verdict = (cobj or {}).get("verdict", "fail")
        confidence = float((cobj or {}).get("confidence", 0.0) or 0.0)
        missing = (cobj or {}).get("missing") or []
        next_search = (cobj or {}).get("next_search") or []
        risk_flags = (cobj or {}).get("risk_flags") or []

        trace.append(
            {
                "loop": loop_idx,
                "plan": candidate_plan,
                "critic": {
                    "verdict": verdict,
                    "confidence": confidence,
                    "missing": missing,
                    "next_search": next_search,
                    "risk_flags": risk_flags,
                },
                "evidence_top3": preview,
            }
        )

        # 5) Acceptance (simple & YAML-guided)
        endpoint_ok = _valid_endpoint(candidate_plan.get("endpoint", ""), allow_pattern, forbid_patterns)
        method = (candidate_plan.get("method") or "").upper()
        params = candidate_plan.get("params") or {}

        is_read = params.get("action") == (read_template.get("params") or {}).get("action")
        has_feature = "name" in params or "<Feature>" in json.dumps(read_template.get("params") or {})
        is_write = params.get("action") == (write_template.get("params") or {}).get("action")

        # Accept READ when endpoint matches pattern, action=getConfig, and has a 'name' feature
        if endpoint_ok and is_read and has_feature:
            log.info("autogen.accept.read idx=%s conf=%.2f", loop_idx, confidence)
            return _final_ok(candidate_plan, confidence, all_hits, missing, next_search, trace)

        # Accept WRITE only if endpoint OK AND critic didn't flag missing example (when required)
        if endpoint_ok and is_write:
            if not write_req_example or ("example" not in " ".join(missing).lower()):
                log.info("autogen.accept.write idx=%s conf=%.2f", loop_idx, confidence)
                return _final_ok(candidate_plan, confidence, all_hits, missing, next_search, trace)

        # Not accepted → iterate or stop
        if loop_idx >= MAX_LOOPS:
            ask = "Not enough information in docs after iterative search. Missing: " + ", ".join(missing) if missing else "Insufficient information."
            return _final_needs_input(all_hits, trace, missing, reason=ask)

        # Prepare next queries
        if next_search:
            queries = next_search
        else:
            # Fallback: reuse original query to avoid stalling
            queries = queries

    # Shouldn't reach here normally
    return _final_needs_input(all_hits, trace, ["plan not accepted"], reason="Loop budget exhausted")


# -----------------------
# Finalizers
# -----------------------
def _final_ok(candidate_plan: dict, confidence: float, all_hits: List[dict], missing: List[str], next_search: List[str], trace: List[dict]) -> dict:
    # Build evidence summary
    evidence_used = {}
    for h in all_hits:
        k = h.get("doc_path") or "?"
        evidence_used.setdefault(k, []).append(h.get("chunk_idx"))
    evidence_used_list = [{"doc": k, "hits": v[:10]} for k, v in evidence_used.items()]

    # Extract alt terms
    alt_terms: List[str] = []
    for h in all_hits:
        qc = (h.get("hints") or {}).get("query_candidates") or {}
        alt_terms.extend(list(qc.keys()))
    alt_terms = list(dict.fromkeys(alt_terms))[:10]

    tips = [
        "Include exact feature names (e.g., 'AudioEncode') in queries.",
        "Add the word 'example' or 'URL Syntax' to find callable forms.",
        "If changing settings, specify channel/stream.",
    ]

    return {
        "status": "ok",
        "source": "autogen",
        "plan": candidate_plan,
        "confidence": confidence,
        "evidence_used": evidence_used_list[:5],
        "missing_info": missing,
        "recommended_queries": next_search[:6],
        "alt_terms": alt_terms,
        "ask_user": ("; ".join(missing) if missing else None),
        "tips": tips,
        "trace": trace,
    }


def _final_needs_input(all_hits: List[dict], trace: List[dict], needed_fields: List[str], reason: Optional[str] = None) -> dict:
    evidence_used = {}
    for h in all_hits:
        k = h.get("doc_path") or "?"
        evidence_used.setdefault(k, []).append(h.get("chunk_idx"))
    evidence_used_list = [{"doc": k, "hits": v[:10]} for k, v in evidence_used.items()]

    alt_terms: List[str] = []
    for h in all_hits:
        qc = (h.get("hints") or {}).get("query_candidates") or {}
        alt_terms.extend(list(qc.keys()))
    alt_terms = list(dict.fromkeys(alt_terms))[:10]

    # Aggregate recommended queries from critic traces
    recommended_queries: List[str] = []
    for t in trace:
        for qn in t.get("critic", {}).get("next_search", []) or []:
            if qn and qn not in recommended_queries:
                recommended_queries.append(qn)

    tips = [
        "Include exact feature names in queries.",
        "Use the word 'example' or 'URL Syntax'.",
        "Provide required IDs/channel if known to reduce ambiguity.",
    ]

    return {
        "status": "needs_input",
        "reason": reason or "Insufficient information.",
        "evidence_used": evidence_used_list[:5],
        "missing_info": (needed_fields or [])[:6],
        "recommended_queries": recommended_queries[:8],
        "alt_terms": alt_terms,
        "ask_user": ("; ".join((needed_fields or [])[:3]) if needed_fields else None),
        "tips": tips,
        "trace": trace,
    }
