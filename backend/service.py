from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import joblib  # type: ignore[import-not-found]
import pandas as pd  # type: ignore[import-not-found]

from modeling.io_utils import load_table

from .db import dumps_json, exec_sql, fetch_all, fetch_one
from .recommender import (
    recommend_with_reasoning as _fast_recommend,
    format_assistant_text as _format_assistant,
    invalidate_model_cache,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_BIN = "python"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_cmd(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )


# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------

YIELD_KEYWORDS = ["yield", "product_yield", "pct", "conversion", "ee", "selectivity"]


def _infer_target_candidates(columns: List[str]) -> List[str]:
    """Heuristic: pick columns likely to be a yield/target column."""
    candidates = []
    for col in columns:
        cl = col.lower().replace(" ", "_")
        if any(kw in cl for kw in YIELD_KEYWORDS):
            candidates.append(col)
    return candidates or columns[:3]  # fallback: first 3 columns


def register_dataset(
    original_filename: str,
    stored_path: str,
    size_bytes: int,
) -> Dict[str, Any]:
    """Register an uploaded dataset in the DB with column metadata."""
    did = str(uuid.uuid4())
    ts = now_iso()
    name = Path(original_filename).stem

    # Extract column metadata
    try:
        df = load_table(stored_path)
        num_rows = len(df)
        num_cols = len(df.columns)
        columns = list(df.columns)
        target_candidates = _infer_target_candidates(columns)
    except Exception:
        num_rows = None
        num_cols = None
        columns = []
        target_candidates = []

    exec_sql(
        """
        INSERT INTO datasets(id, name, original_filename, stored_path, size_bytes,
                             num_rows, num_cols, columns_json, target_candidates_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            did, name, original_filename, stored_path, size_bytes,
            num_rows, num_cols,
            dumps_json(columns), dumps_json(target_candidates),
            ts,
        ),
    )
    return _parse_dataset_row(fetch_one("SELECT * FROM datasets WHERE id = ?", (did,)))


def _parse_dataset_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    parsed = dict(row)
    parsed["columns"] = json.loads(parsed.pop("columns_json") or "[]")
    parsed["target_candidates"] = json.loads(parsed.pop("target_candidates_json") or "[]")
    return parsed


def list_datasets() -> List[Dict[str, Any]]:
    rows = fetch_all("SELECT * FROM datasets ORDER BY created_at DESC")
    return [_parse_dataset_row(r) for r in rows]


def get_dataset(dataset_id: str) -> Optional[Dict[str, Any]]:
    row = fetch_one("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
    return _parse_dataset_row(row)


def get_dataset_models(dataset_id: str) -> List[Dict[str, Any]]:
    """Return training runs whose dataset_path matches this dataset's stored_path."""
    ds = get_dataset(dataset_id)
    if not ds:
        return []
    rows = fetch_all(
        "SELECT * FROM training_runs WHERE dataset_path = ? AND status = 'completed' ORDER BY created_at DESC",
        (ds["stored_path"],),
    )
    for row in rows:
        row["features"] = json.loads(row.pop("features_json") or "[]")
        row["metrics"] = json.loads(row.pop("metrics_json") or "{}")
    return rows


def create_conversation(title: str) -> Dict[str, Any]:
    cid = str(uuid.uuid4())
    ts = now_iso()
    exec_sql(
        "INSERT INTO conversations(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (cid, title, ts, ts),
    )
    return fetch_one("SELECT * FROM conversations WHERE id = ?", (cid,))


def list_conversations() -> List[Dict[str, Any]]:
    return fetch_all("SELECT * FROM conversations ORDER BY updated_at DESC")


def get_conversation(conversation_id: str) -> Dict[str, Any] | None:
    return fetch_one("SELECT * FROM conversations WHERE id = ?", (conversation_id,))


def add_message(
    conversation_id: str, role: str, content: str, metadata: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    mid = str(uuid.uuid4())
    ts = now_iso()
    exec_sql(
        "INSERT INTO messages(id, conversation_id, role, content, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (mid, conversation_id, role, content, dumps_json(metadata or {}), ts),
    )
    exec_sql(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (ts, conversation_id),
    )
    row = fetch_one("SELECT * FROM messages WHERE id = ?", (mid,))
    if not row:
        raise RuntimeError("Failed to fetch inserted message.")
    row["metadata"] = json.loads(row.pop("metadata_json") or "{}")
    return row


def list_messages(conversation_id: str) -> List[Dict[str, Any]]:
    rows = fetch_all(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,),
    )
    for row in rows:
        row["metadata"] = json.loads(row.pop("metadata_json") or "{}")
    return rows


def _extract_json_object(text: str) -> Dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _rules_intent(user_text: str) -> Dict[str, Any]:
    t = (user_text or "").strip().lower()
    if not t:
        return {"intent": "smalltalk", "confidence": 0.99, "source": "rules", "reason": "empty input"}
    greeting_words = {"hi", "hello", "hey", "yo", "hola", "sup"}
    if t in greeting_words or t.startswith("hello ") or t.startswith("hi "):
        return {"intent": "smalltalk", "confidence": 0.98, "source": "rules", "reason": "greeting pattern"}
    if any(k in t for k in ["paper", "literature", "jacs", "chemical science", "citation", "doi"]):
        return {"intent": "literature", "confidence": 0.95, "source": "rules", "reason": "literature keyword"}
    if any(k in t for k in ["status", "where are we", "summary", "what have we done"]):
        return {"intent": "status", "confidence": 0.93, "source": "rules", "reason": "status keyword"}
    if any(k in t for k in ["next", "recommend", "suggest", "experiment", "run", "follow-up", "follow up"]):
        return {"intent": "recommendation", "confidence": 0.88, "source": "rules", "reason": "recommendation keyword"}
    return {"intent": "other", "confidence": 0.35, "source": "rules", "reason": "no strong rule match"}


def _llm_intent(user_text: str) -> Optional[Dict[str, Any]]:
    api_key = os.getenv("NEBIUS_API_KEY", "")
    if not api_key:
        return None
    base_url = os.getenv("NEBIUS_API_BASE", "https://api.studio.nebius.com/v1")
    model_name = os.getenv("INTENT_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")
    prompt = (
        "Classify user intent into exactly one of: smalltalk, recommendation, literature, status, other. "
        "Return strict JSON only: {\"intent\":...,\"confidence\":0..1,\"reason\":...}. "
        "Use 'other' when uncertain."
    )
    body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.0,
        "max_tokens": 60,
    }
    req = Request(
        url=f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _extract_json_object(content)
        intent = str(parsed.get("intent", "other")).strip().lower()
        if intent not in {"smalltalk", "recommendation", "literature", "status", "other"}:
            intent = "other"
        conf = parsed.get("confidence", 0.5)
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.5
        conf = max(0.0, min(1.0, conf))
        return {
            "intent": intent,
            "confidence": conf,
            "source": "llm",
            "reason": str(parsed.get("reason", "llm classified intent")),
            "model": model_name,
        }
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def classify_intent(user_text: str) -> Dict[str, Any]:
    mode = os.getenv("INTENT_MODE", "hybrid").strip().lower()
    rules = _rules_intent(user_text)
    if mode == "rules":
        return rules
    if mode == "llm":
        llm = _llm_intent(user_text)
        return llm or rules
    # hybrid: use rules when confident; otherwise call cheap LLM classifier.
    if float(rules.get("confidence", 0.0)) >= 0.85:
        return rules
    llm = _llm_intent(user_text)
    if not llm:
        return rules
    if float(llm.get("confidence", 0.0)) < 0.45:
        return {"intent": "other", "confidence": llm.get("confidence", 0.0), "source": "llm", "reason": "low confidence"}
    return llm


def _short_experiment_text(next_experiment: Dict[str, Any]) -> str:
    if not isinstance(next_experiment, dict) or not next_experiment:
        return "the top-ranked candidate from the current search space"
    preferred = [
        "Reactant_1_Short_Hand",
        "Reactant_2_Name",
        "Catalyst_1_Short_Hand",
        "Ligand_Short_Hand",
        "Solvent_1_Short_Hand",
        "catalyst",
        "solvent",
        "temperature",
        "time_h",
    ]
    parts = []
    for k in preferred:
        if k in next_experiment and next_experiment[k] is not None:
            parts.append(f"{k}={next_experiment[k]}")
        if len(parts) >= 4:
            break
    return ", ".join(parts) if parts else "the top-ranked candidate from the current search space"


def _normalize_recommendation_payload(recommendation: Dict[str, Any]) -> Dict[str, Any]:
    rec = recommendation if isinstance(recommendation, dict) else {}
    ranked = rec.get("ranked_candidates") or rec.get("top_candidates") or []
    out_candidates: List[Dict[str, Any]] = []
    for item in ranked:
        if not isinstance(item, dict):
            continue
        out_candidates.append(
            {
                "rank": int(item.get("rank") or (len(out_candidates) + 1)),
                "predicted_yield": item.get("predicted_yield"),
                "predicted_uncertainty": item.get("predicted_uncertainty"),
                "exploit_score": item.get("exploit_score"),
                "explore_bonus": item.get("explore_bonus"),
                "ucb_score": item.get("ucb_score"),
                "conditions": item.get("params") or item.get("conditions") or {},
                "reasoning": item.get("reasoning"),
            }
        )
    out = {
        "model_path": rec.get("model_path"),
        "strategy": rec.get("ranking_method") or rec.get("strategy"),
        "predicted_yield": rec.get("predicted_yield"),
        "predicted_uncertainty": rec.get("predicted_uncertainty"),
        "next_experiment": rec.get("next_experiment") or {},
        "top_candidates": out_candidates,
        # Backward-compatible alias for current frontend rendering.
        "ranked_candidates": out_candidates,
    }
    return out


def _normalize_reasoning_payload(reasoning: Dict[str, Any]) -> Dict[str, Any]:
    r = reasoning if isinstance(reasoning, dict) else {}
    # Keep one stable contract even when upstream script changes key names.
    out = {
        "summary": r.get("summary"),
        "why_now": r.get("why_now"),
        "confidence_note": r.get("confidence_note") or r.get("confidence"),
        "cautionary_note": r.get("cautionary_note") or r.get("caution_note"),
        "decision_rule_after_result": r.get("decision_rule_after_result"),
        "justification_source": r.get("justification_source"),
        # Backward-compatible aliases for existing UI.
        "confidence": r.get("confidence"),
        "caution_note": r.get("caution_note") or r.get("cautionary_note"),
    }
    return out


def _normalize_evidence_payload(evidence: Dict[str, Any]) -> Dict[str, Any]:
    e = evidence if isinstance(evidence, dict) else {}
    rows = []
    for item in e.get("results", []) or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "title": str(item.get("title", "") or ""),
                "url": str(item.get("url", "") or ""),
                "snippet": str(item.get("snippet", "") or ""),
                "score": item.get("score"),
                "matched_journals": item.get("matched_journals") or [],
                "has_preferred_journal_hint": bool(item.get("has_preferred_journal_hint", False)),
                "doi_hint": item.get("doi_hint"),
            }
        )
    return {
        "status": str(e.get("status", "unknown") or "unknown"),
        "query": str(e.get("query", "") or ""),
        "answer": e.get("answer"),
        "results": rows,
        "message": e.get("message"),
    }


def run_agent_turn(
    conversation_id: str,
    user_text: str,
    data_path: str,
    model_path: str,
    top_k: int,
    use_llm: bool,
    use_tavily: bool,
) -> Dict[str, Any]:
    intent_info = classify_intent(user_text)
    intent = str(intent_info.get("intent", "other"))
    add_message(
        conversation_id,
        "user",
        user_text,
        metadata={"type": "user_prompt", "intent": intent, "intent_classifier": intent_info},
    )

    if intent == "smalltalk":
        return add_message(
            conversation_id,
            "assistant",
            (
                "Hi! I can recommend the next best experiment, explain why, and show supporting literature. "
                "Try: 'Recommend a simple starter experiment and one follow-up based on expected outcome.'"
            ),
            metadata={"intent": intent, "route": "smalltalk", "intent_classifier": intent_info},
        )

    if intent == "status":
        prior = list_messages(conversation_id)
        assistant_count = sum(1 for m in prior if m.get("role") == "assistant")
        user_count = sum(1 for m in prior if m.get("role") == "user")
        last_assistant = next((m for m in reversed(prior) if m.get("role") == "assistant"), None)
        snippet = (last_assistant or {}).get("content", "")
        return add_message(
            conversation_id,
            "assistant",
            (
                f"Thread status: {user_count} user messages, {assistant_count} assistant messages. "
                f"Latest assistant update: {snippet[:220]}"
            ),
            metadata={"intent": intent, "route": "status", "intent_classifier": intent_info},
        )

    if intent == "other":
        return add_message(
            conversation_id,
            "assistant",
            (
                "I can help with: (1) next experiment recommendation, (2) literature support, or (3) campaign status. "
                "Tell me which one you want."
            ),
            metadata={"intent": intent, "route": "clarify", "intent_classifier": intent_info},
        )

    if intent == "literature":
        lit = explain_literature_relevance(
            query=user_text,
            data_path=data_path,
            model_path=model_path,
            top_k=min(max(int(top_k), 1), 3),
            use_llm=use_llm,
            max_results=5,
            search_depth="advanced",
            include_answer="basic",
            focus_journals=["JACS", "Chemical Science"],
        )
        relevance = lit.get("relevance", {}) or {}
        level = str(relevance.get("level", "medium"))
        why_related = (relevance.get("why_related", []) or [])[:2]
        followups = (lit.get("actionable_followups", []) or [])[:2]
        assistant_text = (
            f"Literature review summary: {lit.get('paper_summary') or 'No concise summary available.'} "
            f"Relevance to your work: {level}. "
            f"Why: {'; '.join(str(x) for x in why_related) if why_related else 'Evidence partially matches your query context.'} "
            f"Suggested next checks: {'; '.join(str(x) for x in followups) if followups else 'Run one confirmatory experiment before broad changes.'}"
        ).strip()
        evidence = lit.get("evidence", {}) or {}
        return add_message(
            conversation_id,
            "assistant",
            assistant_text,
            metadata={
                "intent": intent,
                "intent_classifier": intent_info,
                "route": "literature_explain",
                "agent_trace": [
                    {"step": 1, "tool": "intent_classifier", "status": "success"},
                    {"step": 2, "tool": "literature.explain", "status": "success"},
                    {"step": 3, "tool": "literature.tavily_search", "status": evidence.get("status", "unknown")},
                ],
                "literature_explain": lit,
                "recommendation": lit.get("recommendation_context", {}) or {},
                "reasoning": {
                    "why_now": None,
                    "caution_note": "; ".join((relevance.get("gaps", []) or [])[:2]),
                    "decision_rule_after_result": "; ".join(followups),
                    "confidence": level,
                },
                "evidence": evidence,
                "tavily_mode": "explicit_literature",
                "llm_error": None,
                "artifacts": {},
            },
        )

    auto_threshold = float(os.getenv("TAVILY_AUTO_UNCERTAINTY_THRESHOLD", "10.0"))
    tavily_mode = "disabled"

    # Build exclusion set from conversation history (previously recommended row_indices)
    exclude_indices: set = set()
    try:
        prior = list_messages(conversation_id)
        for m in prior:
            mm = m.get("metadata") or {}
            rec_meta = mm.get("recommendation") or {}
            for cand in rec_meta.get("ranked_candidates", []) or rec_meta.get("top_candidates", []) or []:
                ri = cand.get("row_index")
                if ri is not None:
                    exclude_indices.add(int(ri))
    except Exception:
        pass

    payload: Dict[str, Any]
    if use_tavily:
        payload = run_recommendation_with_evidence(
            data_path=data_path,
            model_path=model_path,
            top_k=top_k,
            use_llm=use_llm,
            evidence_query=None,
            evidence_max_results=5,
            search_depth="advanced",
            include_answer="basic",
            focus_journals=["JACS", "Chemical Science"],
            exclude_indices=exclude_indices,
        )
        tavily_mode = "explicit"
    else:
        payload = run_recommendation_with_reasoning(
            data_path=data_path,
            model_path=model_path,
            top_k=top_k,
            use_llm=use_llm,
            exclude_indices=exclude_indices,
        )
        rec = payload.get("recommendation", {}) or {}
        uncertainty = rec.get("predicted_uncertainty")
        try:
            uncertainty_val = float(uncertainty) if uncertainty is not None else None
        except (TypeError, ValueError):
            uncertainty_val = None
        if uncertainty_val is not None and uncertainty_val >= auto_threshold:
            query = _build_literature_query_from_recommendation(rec)
            payload["evidence"] = search_literature_evidence(
                query=query,
                max_results=5,
                search_depth="advanced",
                include_answer="basic",
                focus_journals=["JACS", "Chemical Science"],
            )
            tavily_mode = "auto_high_uncertainty"

    recommendation = payload.get("recommendation", {}) or {}
    reasoning = payload.get("reasoning", {}) or {}
    evidence = payload.get("evidence", {}) or {}

    # Build clean, structured assistant text
    assistant_text = _format_assistant(recommendation, reasoning, evidence if evidence else None)

    agent_trace = [
        {"step": 1, "tool": "intent_classifier", "status": "success"},
        {"step": 2, "tool": "optimizer.recommend_next", "status": "success"},
        {"step": 3, "tool": "reasoning.explainer", "status": "success"},
    ]
    if use_tavily:
        agent_trace.append({"step": 4, "tool": "literature.tavily_search", "status": evidence.get("status", "unknown")})
    elif tavily_mode == "auto_high_uncertainty":
        agent_trace.append(
            {
                "step": 4,
                "tool": "literature.tavily_search",
                "status": evidence.get("status", "unknown"),
                "trigger": f"predicted_uncertainty>={auto_threshold}",
            }
        )

    return add_message(
        conversation_id,
        "assistant",
        assistant_text,
        metadata={
            "intent": intent,
            "intent_classifier": intent_info,
            "route": "recommendation_pipeline",
            "agent_trace": agent_trace,
            "recommendation": recommendation,
            "reasoning": reasoning,
            "evidence": evidence,
            "tavily_mode": tavily_mode,
            "tavily_auto_uncertainty_threshold": auto_threshold,
            "llm_error": payload.get("llm_error"),
            "artifacts": payload.get("artifacts", {}),
        },
    )


def run_recommendation_with_reasoning(
    data_path: str,
    model_path: str,
    top_k: int = 5,
    use_llm: bool = False,
    exclude_indices: Optional[set] = None,
) -> Dict[str, Any]:
    """Fast in-process recommendation + reasoning (no subprocess)."""
    result = _fast_recommend(
        data_path=data_path,
        model_path=model_path,
        top_k=top_k,
        use_llm=use_llm,
        exclude_indices=exclude_indices,
    )
    return {
        "recommendation": _normalize_recommendation_payload(result.get("recommendation", {})),
        "reasoning": _normalize_reasoning_payload(result.get("reasoning", {})),
        "llm_error": result.get("llm_error"),
        "artifacts": {},
    }


def _build_literature_query_from_recommendation(recommendation: Dict[str, Any]) -> str:
    next_exp = recommendation.get("next_experiment", {}) if isinstance(recommendation, dict) else {}
    query_tokens = []
    preferred_keys = ["Catalyst_1_Short_Hand", "Ligand_Short_Hand", "Solvent_1_Short_Hand", "catalyst", "solvent"]
    for key in preferred_keys:
        val = next_exp.get(key)
        if val is not None and str(val).strip():
            query_tokens.append(str(val).strip())
    if not query_tokens:
        return "reaction optimization next best experiment conditions high yield uncertainty analysis"
    return f"reaction optimization {' '.join(query_tokens)} yield condition screening"


def search_literature_evidence(
    query: str,
    max_results: int = 5,
    search_depth: str = "advanced",
    include_answer: str = "basic",
    focus_journals: Optional[List[str]] = None,
) -> Dict[str, Any]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return {
            "status": "missing_api_key",
            "message": "TAVILY_API_KEY is not set. Add it to your .env and restart backend.",
            "query": query,
            "results": [],
        }

    try:
        from tavily import TavilyClient  # type: ignore[import-not-found]
    except ImportError:
        return {
            "status": "missing_dependency",
            "message": "tavily-python is not installed. Run: pip install tavily-python",
            "query": query,
            "results": [],
        }

    focus_journals = focus_journals or ["JACS", "Chemical Science"]
    scoped_query = (
        f"{query} (\"Journal of the American Chemical Society\" OR \"Chemical Science\" OR site:pubs.acs.org OR site:rsc.org)"
    )

    client = TavilyClient(api_key)
    try:
        raw = client.search(
            query=scoped_query,
            include_answer=include_answer,
            search_depth=search_depth,
            max_results=max_results,
        )
    except TypeError:
        raw = client.search(
            query=scoped_query,
            include_answer=include_answer,
            search_depth=search_depth,
        )
    except Exception as exc:  # pragma: no cover - external API failures
        return {
            "status": "error",
            "message": str(exc),
            "query": scoped_query,
            "results": [],
        }

    def clean_text(value: str) -> str:
        # Some upstream snippets include raw control/newline chars; normalize for strict JSON clients.
        normalized = re.sub(r"[\x00-\x1F]+", " ", value or "")
        return re.sub(r"\s+", " ", normalized).strip()

    rows = []
    for item in raw.get("results", [])[:max_results]:
        title = clean_text(item.get("title", "") or "")
        url = clean_text(item.get("url", "") or "")
        content = clean_text(item.get("content", "") or "")
        blob = f"{title} {url} {content}".lower()
        matched = [j for j in focus_journals if j.lower() in blob]
        doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", blob, flags=re.IGNORECASE)
        rows.append(
            {
                "title": title,
                "url": url,
                "snippet": content[:700],
                "score": item.get("score"),
                "matched_journals": matched,
                "has_preferred_journal_hint": bool(matched),
                "doi_hint": doi_match.group(0) if doi_match else None,
            }
        )

    return {
        "status": "ok",
        "query": scoped_query,
        "answer": raw.get("answer"),
        "results": rows,
    }


def run_recommendation_with_evidence(
    data_path: str,
    model_path: str,
    top_k: int = 5,
    use_llm: bool = False,
    evidence_query: Optional[str] = None,
    evidence_max_results: int = 5,
    search_depth: str = "advanced",
    include_answer: str = "basic",
    focus_journals: Optional[List[str]] = None,
    exclude_indices: Optional[set] = None,
) -> Dict[str, Any]:
    rec = run_recommendation_with_reasoning(
        data_path=data_path,
        model_path=model_path,
        top_k=top_k,
        use_llm=use_llm,
        exclude_indices=exclude_indices,
    )
    recommendation_payload = rec.get("recommendation", {})
    query = evidence_query or _build_literature_query_from_recommendation(recommendation_payload)
    evidence = search_literature_evidence(
        query=query,
        max_results=evidence_max_results,
        search_depth=search_depth,
        include_answer=include_answer,
        focus_journals=focus_journals,
    )
    rec["evidence"] = _normalize_evidence_payload(evidence)
    return rec


def explain_literature_relevance(
    query: str,
    data_path: Optional[str] = None,
    model_path: Optional[str] = None,
    top_k: int = 3,
    use_llm: bool = False,
    max_results: int = 5,
    search_depth: str = "advanced",
    include_answer: str = "basic",
    focus_journals: Optional[List[str]] = None,
) -> Dict[str, Any]:
    recommendation_context: Optional[Dict[str, Any]] = None
    recommendation_warning: Optional[str] = None
    if data_path and model_path:
        try:
            rec = run_recommendation_with_reasoning(
                data_path=data_path,
                model_path=model_path,
                top_k=top_k,
                use_llm=use_llm,
            )
            recommendation_context = rec.get("recommendation", {})
        except subprocess.CalledProcessError:
            recommendation_warning = (
                "Could not build recommendation context for this dataset/model pair. "
                "Literature explanation is returned without recommendation context."
            )

    evidence = _normalize_evidence_payload(
        search_literature_evidence(
            query=query,
            max_results=max_results,
            search_depth=search_depth,
            include_answer=include_answer,
            focus_journals=focus_journals,
        )
    )

    next_experiment = (recommendation_context or {}).get("next_experiment", {})
    condition_tokens = [str(v).lower() for v in (next_experiment or {}).values() if v is not None][:8]
    corpus = " ".join([str(evidence.get("answer", "") or "")] + [str(r.get("snippet", "") or "") for r in evidence.get("results", [])]).lower()
    overlap = sum(1 for t in condition_tokens if t and t in corpus)
    if overlap >= 3:
        level = "high"
    elif overlap >= 1:
        level = "medium"
    else:
        level = "low"

    why_related = []
    if query.strip():
        why_related.append("Literature retrieval was scoped to the scientist's explicit question.")
    if overlap > 0:
        why_related.append("At least one recommended condition token appears in retrieved evidence snippets.")
    if (evidence.get("results") or []):
        why_related.append("Supporting citations were retrieved from chemistry-focused sources.")

    assumptions = [
        "Paper conditions transfer only if substrate/reactivity context is comparable.",
        "Reported conditions may require adaptation for scale, equipment, or constraints.",
    ]
    if recommendation_warning:
        assumptions.append(recommendation_warning)
    gaps = [
        "Evidence snippets are not mechanistic proof for your exact substrate pair.",
        "If relevance is low, run one confirmatory micro-experiment before broad rollout.",
    ]
    followups = [
        "Run the top recommendation as-is and log observed yield.",
        "Run one contrast experiment changing only catalyst or ligand to isolate transfer effect.",
    ]

    return {
        "query": query,
        "recommendation_context": recommendation_context,
        "paper_summary": evidence.get("answer"),
        "relevance": {
            "level": level,
            "why_related": why_related,
            "assumptions": assumptions,
            "gaps": gaps,
        },
        "actionable_followups": followups,
        "evidence": evidence,
    }


def create_training_run(
    dataset_path: str,
    target_column: str,
    features: List[str],
    output_name: str,
) -> Dict[str, Any]:
    run_id = str(uuid.uuid4())
    ts = now_iso()
    exec_sql(
        """
        INSERT INTO training_runs(id, status, dataset_path, target_column, features_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, "running", dataset_path, target_column, dumps_json(features), ts, ts),
    )

    model_path = PROJECT_ROOT / "artifacts" / f"{output_name}_{run_id}.joblib"
    meta_path = PROJECT_ROOT / "artifacts" / f"{output_name}_{run_id}_meta.json"
    cmd = [
        PYTHON_BIN,
        "train_surrogate.py",
        "--data",
        dataset_path,
        "--target",
        target_column,
        "--out-model",
        str(model_path),
        "--out-meta",
        str(meta_path),
    ]
    if features:
        cmd += ["--features", ",".join(features)]

    try:
        run_cmd(cmd)
        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        exec_sql(
            """
            UPDATE training_runs
            SET status=?, model_path=?, meta_path=?, metrics_json=?, updated_at=?
            WHERE id=?
            """,
            ("completed", str(model_path), str(meta_path), dumps_json(meta.get("metrics", {})), now_iso(), run_id),
        )
    except subprocess.CalledProcessError as e:
        exec_sql(
            "UPDATE training_runs SET status=?, error_text=?, updated_at=? WHERE id=?",
            ("failed", e.stderr[-2000:], now_iso(), run_id),
        )

    return get_training_run(run_id)


def list_training_runs() -> List[Dict[str, Any]]:
    rows = fetch_all("SELECT * FROM training_runs ORDER BY created_at DESC")
    for row in rows:
        row["features"] = json.loads(row.pop("features_json") or "[]")
        row["metrics"] = json.loads(row.pop("metrics_json") or "{}")
    return rows


def get_training_run(run_id: str) -> Dict[str, Any] | None:
    row = fetch_one("SELECT * FROM training_runs WHERE id = ?", (run_id,))
    if not row:
        return None
    row["features"] = json.loads(row.pop("features_json") or "[]")
    row["metrics"] = json.loads(row.pop("metrics_json") or "{}")
    return row


def create_experiment_run(
    strategy: str,
    dataset_path: str,
    model_path: str,
    budget: int,
    n_init: int,
    seed: int,
    reward_mode: str,
    beta: float,
    linucb_alpha: float,
    linucb_lambda: float,
) -> Dict[str, Any]:
    run_id = str(uuid.uuid4())
    ts = now_iso()
    exec_sql(
        """
        INSERT INTO experiment_runs(id, status, strategy, dataset_path, model_path, budget, n_init, seed, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, "running", strategy, dataset_path, model_path, budget, n_init, seed, ts, ts),
    )

    out_path = PROJECT_ROOT / "artifacts" / f"experiment_run_{run_id}.json"
    cmd = [
        PYTHON_BIN,
        "simulate_optimization.py",
        "--data",
        dataset_path,
        "--model",
        model_path,
        "--strategy",
        strategy,
        "--budget",
        str(budget),
        "--n-init",
        str(n_init),
        "--seed",
        str(seed),
        "--out",
        str(out_path),
    ]
    if strategy == "adaptive":
        cmd += ["--beta", str(beta)]
    elif strategy == "contextual_linucb":
        cmd += [
            "--reward-mode",
            reward_mode,
            "--linucb-alpha",
            str(linucb_alpha),
            "--linucb-lambda",
            str(linucb_lambda),
        ]
    elif strategy == "bandit_ucb":
        cmd += ["--reward-mode", reward_mode]
    elif strategy == "greedy":
        cmd[cmd.index("--strategy") + 1] = "adaptive"
        cmd += ["--beta", "0.0"]

    try:
        run_cmd(cmd)
        with out_path.open("r", encoding="utf-8") as f:
            result = json.load(f)
        summary = {
            "best_yield": result.get("best_yield"),
            "steps_completed": result.get("steps_completed"),
            "strategy": result.get("strategy"),
        }
        exec_sql(
            """
            UPDATE experiment_runs
            SET status=?, output_path=?, summary_json=?, updated_at=?
            WHERE id=?
            """,
            ("completed", str(out_path), dumps_json(summary), now_iso(), run_id),
        )
    except subprocess.CalledProcessError as e:
        exec_sql(
            "UPDATE experiment_runs SET status=?, error_text=?, updated_at=? WHERE id=?",
            ("failed", e.stderr[-2000:], now_iso(), run_id),
        )

    return get_experiment_run(run_id)


def list_experiment_runs() -> List[Dict[str, Any]]:
    rows = fetch_all("SELECT * FROM experiment_runs ORDER BY created_at DESC")
    for row in rows:
        row["summary"] = json.loads(row.pop("summary_json") or "{}")
    return rows


def get_experiment_run(run_id: str) -> Dict[str, Any] | None:
    row = fetch_one("SELECT * FROM experiment_runs WHERE id = ?", (run_id,))
    if not row:
        return None
    row["summary"] = json.loads(row.pop("summary_json") or "{}")
    return row


def _parse_session_row(row: Dict[str, Any]) -> Dict[str, Any]:
    parsed = dict(row)
    parsed["use_llm"] = bool(parsed.get("use_llm", 0))
    parsed["use_tavily"] = bool(parsed.get("use_tavily", 0))
    parsed["last_recommendation"] = json.loads(parsed.pop("last_recommendation_json") or "{}")
    parsed["last_reasoning"] = json.loads(parsed.pop("last_reasoning_json") or "{}")
    parsed["last_evidence"] = json.loads(parsed.pop("last_evidence_json") or "{}")
    return parsed


def create_session(
    title: str,
    conversation_id: Optional[str],
    dataset_path: str,
    model_path: str,
    budget: int,
    top_k: int,
    use_llm: bool,
    use_tavily: bool,
) -> Dict[str, Any]:
    sid = str(uuid.uuid4())
    ts = now_iso()
    exec_sql(
        """
        INSERT INTO sessions(
            id, title, conversation_id, dataset_path, model_path, budget, top_k, use_llm, use_tavily, status,
            best_observed_yield, steps_completed, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sid,
            title,
            conversation_id,
            dataset_path,
            model_path,
            budget,
            top_k,
            int(use_llm),
            int(use_tavily),
            "active",
            None,
            0,
            ts,
            ts,
        ),
    )
    row = fetch_one("SELECT * FROM sessions WHERE id = ?", (sid,))
    if not row:
        raise RuntimeError("Failed to create session.")
    return _parse_session_row(row)


def list_sessions() -> List[Dict[str, Any]]:
    rows = fetch_all("SELECT * FROM sessions ORDER BY updated_at DESC")
    return [_parse_session_row(r) for r in rows]


def get_session(session_id: str) -> Dict[str, Any] | None:
    row = fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
    return _parse_session_row(row) if row else None


def _list_session_results(session_id: str) -> List[Dict[str, Any]]:
    rows = fetch_all(
        "SELECT * FROM session_results WHERE session_id = ? ORDER BY step_index ASC, created_at ASC",
        (session_id,),
    )
    out = []
    for r in rows:
        row = dict(r)
        row["recommendation"] = json.loads(row.pop("recommendation_json") or "{}")
        row["metadata"] = json.loads(row.pop("metadata_json") or "{}")
        out.append(row)
    return out


def _build_adapted_model_for_session(session_id: str, sess: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Build an adapted model by augmenting the base dataset with user-submitted
    conditions + observed yields from this session.
    Returns metadata dict when retrain succeeds, else None.
    """
    results = _list_session_results(session_id)
    if not results:
        return None

    bundle = joblib.load(sess["model_path"])
    feature_columns = bundle.get("feature_columns", [])
    target_column = bundle.get("target_column")
    if not feature_columns or not target_column:
        return None

    rows: List[Dict[str, Any]] = []
    for r in results:
        meta = r.get("metadata", {}) or {}
        conditions = meta.get("conditions", {}) or {}
        if not isinstance(conditions, dict):
            conditions = {}
        # Backward-compat fallback: use last recommended next_experiment if explicit
        # conditions were not submitted by the client.
        if not conditions:
            rec = r.get("recommendation", {}) or {}
            conditions = rec.get("next_experiment", {}) or {}
        if not isinstance(conditions, dict):
            continue
        row = {col: conditions.get(col) for col in feature_columns}
        row[target_column] = r.get("observed_yield")
        rows.append(row)

    if not rows:
        return None

    base_df = load_table(sess["dataset_path"])
    add_df = pd.DataFrame(rows)
    combined = pd.concat([base_df, add_df], ignore_index=True, sort=False)

    suffix = uuid.uuid4().hex[:8]
    combined_path = PROJECT_ROOT / "artifacts" / f"session_{session_id}_{suffix}_augmented.csv"
    model_path = PROJECT_ROOT / "artifacts" / f"session_{session_id}_{suffix}_adapted.joblib"
    meta_path = PROJECT_ROOT / "artifacts" / f"session_{session_id}_{suffix}_adapted_meta.json"
    combined.to_csv(combined_path, index=False)

    cmd = [
        PYTHON_BIN,
        "train_surrogate.py",
        "--data",
        str(combined_path),
        "--target",
        str(target_column),
        "--features",
        ",".join(feature_columns),
        "--out-model",
        str(model_path),
        "--out-meta",
        str(meta_path),
    ]
    run_cmd(cmd)
    return {
        "model_path": str(model_path),
        "meta_path": str(meta_path),
        "combined_dataset_path": str(combined_path),
        "augmented_rows": len(rows),
    }


def get_session_state(session_id: str) -> Dict[str, Any] | None:
    sess = get_session(session_id)
    if not sess:
        return None
    results = _list_session_results(session_id)
    remaining_budget = max(int(sess["budget"]) - int(sess["steps_completed"]), 0)
    return {
        "session": sess,
        "results": results,
        "remaining_budget": remaining_budget,
    }


def session_next_recommendation(
    session_id: str,
    top_k: Optional[int] = None,
    use_llm: Optional[bool] = None,
    use_tavily: Optional[bool] = None,
) -> Dict[str, Any]:
    sess = get_session(session_id)
    if not sess:
        raise ValueError("Session not found.")
    if sess["status"] != "active":
        raise ValueError("Session is not active.")
    if int(sess["steps_completed"]) >= int(sess["budget"]):
        raise ValueError("Budget exhausted. Submit no more results for this session.")

    final_top_k = int(top_k if top_k is not None else sess["top_k"])
    final_use_llm = bool(sess["use_llm"] if use_llm is None else use_llm)
    final_use_tavily = bool(sess["use_tavily"] if use_tavily is None else use_tavily)

    if final_use_tavily:
        payload = run_recommendation_with_evidence(
            data_path=sess["dataset_path"],
            model_path=sess["model_path"],
            top_k=final_top_k,
            use_llm=final_use_llm,
        )
    else:
        payload = run_recommendation_with_reasoning(
            data_path=sess["dataset_path"],
            model_path=sess["model_path"],
            top_k=final_top_k,
            use_llm=final_use_llm,
        )

    ts = now_iso()
    exec_sql(
        """
        UPDATE sessions
        SET top_k=?, use_llm=?, use_tavily=?, last_recommendation_json=?, last_reasoning_json=?, last_evidence_json=?, updated_at=?
        WHERE id=?
        """,
        (
            final_top_k,
            int(final_use_llm),
            int(final_use_tavily),
            dumps_json(payload.get("recommendation", {})),
            dumps_json(payload.get("reasoning", {})),
            dumps_json(payload.get("evidence", {})),
            ts,
            session_id,
        ),
    )
    return {
        "session_id": session_id,
        "step_index": int(sess["steps_completed"]) + 1,
        **payload,
    }


def session_submit_result(
    session_id: str,
    observed_yield: float,
    notes: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    conditions: Optional[Dict[str, Any]] = None,
    recommendation_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sess = get_session(session_id)
    if not sess:
        raise ValueError("Session not found.")
    if sess["status"] != "active":
        raise ValueError("Session is not active.")
    if int(sess["steps_completed"]) >= int(sess["budget"]):
        raise ValueError("Budget exhausted for this session.")

    current_step = int(sess["steps_completed"]) + 1
    recommendation_payload = recommendation_override if recommendation_override is not None else sess.get("last_recommendation", {})
    stored_metadata = dict(metadata or {})
    if conditions:
        stored_metadata["conditions"] = conditions
    rid = str(uuid.uuid4())
    ts = now_iso()
    exec_sql(
        """
        INSERT INTO session_results(
            id, session_id, step_index, recommendation_json, observed_yield, notes, metadata_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rid,
            session_id,
            current_step,
            dumps_json(recommendation_payload),
            float(observed_yield),
            notes,
            dumps_json(stored_metadata),
            ts,
        ),
    )

    prev_best = sess.get("best_observed_yield")
    next_best = float(observed_yield) if prev_best is None else max(float(prev_best), float(observed_yield))
    new_steps = current_step
    new_status = "completed" if new_steps >= int(sess["budget"]) else "active"
    exec_sql(
        """
        UPDATE sessions
        SET best_observed_yield=?, steps_completed=?, status=?, updated_at=?
        WHERE id=?
        """,
        (next_best, new_steps, new_status, now_iso(), session_id),
    )
    # Re-train adapted model with submitted session runs so future recommendations
    # reflect user-provided conditions + observed yields.
    try:
        updated_sess = get_session(session_id)
        if updated_sess:
            adapted = _build_adapted_model_for_session(session_id, updated_sess)
            if adapted and adapted.get("model_path"):
                exec_sql(
                    "UPDATE sessions SET model_path=?, updated_at=? WHERE id=?",
                    (adapted["model_path"], now_iso(), session_id),
                )
    except Exception:
        # Keep submit path resilient; recommendation can still proceed with base model.
        pass

    # Mirror session updates into linked conversation thread when available.
    conversation_id = sess.get("conversation_id")
    if conversation_id:
        try:
            result_text = (
                f"Observed outcome recorded for step {current_step}: yield={float(observed_yield):.2f}. "
                f"{'Notes: ' + notes if notes else ''}"
            ).strip()
            add_message(
                conversation_id,
                "user",
                result_text,
                metadata={
                    "type": "session_result",
                    "session_id": session_id,
                    "step_index": current_step,
                    "conditions": conditions or {},
                    "observed_yield": float(observed_yield),
                },
            )
            # If budget remains, proactively post the next recommendation in the same thread.
            if new_status == "active":
                next_payload = session_next_recommendation(
                    session_id=session_id,
                    top_k=int(sess["top_k"]),
                    use_llm=bool(sess["use_llm"]),
                    use_tavily=bool(sess["use_tavily"]),
                )
                rec = next_payload.get("recommendation", {}) or {}
                reason = next_payload.get("reasoning", {}) or {}
                assistant_text = (
                    "Based on your submitted result, next recommendation: run "
                    f"{_short_experiment_text(rec.get('next_experiment', {}) or {})}. "
                    f"Why now: {reason.get('why_now', 'Best expected tradeoff between yield and learning.')}"
                )
                add_message(
                    conversation_id,
                    "assistant",
                    assistant_text,
                    metadata={
                        "type": "session_auto_followup",
                        "session_id": session_id,
                        "step_index": current_step + 1,
                        "recommendation": rec,
                        "reasoning": reason,
                        "evidence": next_payload.get("evidence", {}),
                        "llm_error": next_payload.get("llm_error"),
                        "artifacts": next_payload.get("artifacts", {}),
                    },
                )
        except Exception:
            # Keep submit resilient even if chat mirroring fails.
            pass

    state = get_session_state(session_id)
    if not state:
        raise RuntimeError("Failed to load session state after submit.")
    return state


def _latest_artifact(pattern: str) -> Optional[Path]:
    matches = sorted((PROJECT_ROOT / "artifacts").glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def get_evaluation_snapshot() -> Dict[str, Any]:
    """
    Fair-eval snapshot built from benchmark artifacts (holdout-first) plus live run counts.
    """
    generalization_path = _latest_artifact("benchmark_generalization*.json")
    ranking_path = _latest_artifact("benchmark_label_ranking*.json")

    generalization: Dict[str, Any] = {}
    ranking: Dict[str, Any] = {}
    if generalization_path and generalization_path.exists():
        generalization = json.loads(generalization_path.read_text(encoding="utf-8"))
    if ranking_path and ranking_path.exists():
        ranking = json.loads(ranking_path.read_text(encoding="utf-8"))

    strategies = []
    aggregates = (generalization.get("aggregates") or {}) if isinstance(generalization, dict) else {}
    for name, vals in aggregates.items():
        if not isinstance(vals, dict):
            continue
        strategies.append(
            {
                "name": name,
                "n_runs": vals.get("n_runs"),
                "best_yield_mean": vals.get("best_yield_mean"),
                "best_yield_std": vals.get("best_yield_std"),
                "trajectory_auc_mean": vals.get("trajectory_auc_mean"),
                "trajectory_auc_std": vals.get("trajectory_auc_std"),
                "threshold_hit_rate": vals.get("threshold_hit_rate"),
                "avg_step_to_threshold_when_hit": vals.get("avg_step_to_threshold_when_hit"),
                "best_uplift_vs_random_mean": vals.get("best_uplift_vs_random_mean"),
                "auc_uplift_vs_random_mean": vals.get("auc_uplift_vs_random_mean"),
                "win_rate_vs_random": vals.get("win_rate_vs_random"),
            }
        )

    # Sort by mean best yield for presentation.
    strategies.sort(key=lambda x: float(x.get("best_yield_mean") or -1), reverse=True)

    ranking_aggs = (ranking.get("aggregates") or {}) if isinstance(ranking, dict) else {}
    lr = ranking_aggs.get("label_ranking_style", {}) if isinstance(ranking_aggs, dict) else {}
    rb = ranking_aggs.get("random_baseline", {}) if isinstance(ranking_aggs, dict) else {}
    ranking_delta = {
        "top1_delta": (lr.get("top1_mean") or 0) - (rb.get("top1_mean") or 0),
        "top3_delta": (lr.get("top3_mean") or 0) - (rb.get("top3_mean") or 0),
        "top5_delta": (lr.get("top5_mean") or 0) - (rb.get("top5_mean") or 0),
        "mrr_delta": (lr.get("mrr_mean") or 0) - (rb.get("mrr_mean") or 0),
    }

    live_runs = list_experiment_runs()
    return {
        "methodology": {
            "policy": "holdout-first",
            "notes": [
                "Generalization metrics come from group-holdout benchmark artifacts.",
                "In-distribution single-run numbers are not used for core claims.",
                "Label ranking is reported separately against random baseline.",
            ],
        },
        "sources": {
            "generalization_artifact": str(generalization_path) if generalization_path else None,
            "ranking_artifact": str(ranking_path) if ranking_path else None,
        },
        "generalization": {
            "config": generalization.get("config", {}),
            "strategies": strategies,
        },
        "label_ranking": {
            "config": ranking.get("config", {}),
            "dataset_stats": ranking.get("dataset_stats", {}),
            "label_ranking_style": lr,
            "random_baseline": rb,
            "delta_vs_random": ranking_delta,
        },
        "live_runs_summary": {
            "count": len(live_runs),
        },
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def select_best_training_model() -> Optional[Dict[str, Any]]:
    """
    Pick best completed training run primarily by R2 (desc), then MAE (asc).
    """
    rows = list_training_runs()
    completed = [r for r in rows if r.get("status") == "completed" and r.get("model_path")]
    if not completed:
        return None

    def score(row: Dict[str, Any]) -> tuple[float, float]:
        metrics = row.get("metrics", {}) or {}
        r2 = _safe_float(metrics.get("r2"), default=-1e9)
        mae = _safe_float(metrics.get("mae"), default=1e9)
        return (r2, -mae)

    best = sorted(completed, key=score, reverse=True)[0]
    metrics = best.get("metrics", {}) or {}
    return {
        "run_id": best.get("id"),
        "model_path": best.get("model_path"),
        "dataset_path": best.get("dataset_path"),
        "metrics": {"r2": metrics.get("r2"), "mae": metrics.get("mae"), "rmse": metrics.get("rmse")},
        "selection_reason": "highest_r2_then_lowest_mae",
    }


def run_comparison_suite(
    dataset_path: str,
    model_path: Optional[str],
    strategies: Optional[List[str]] = None,
    seeds: Optional[List[int]] = None,
    budget: int = 20,
    n_init: int = 3,
    reward_mode: str = "improvement",
    beta: float = 0.8,
    linucb_alpha: float = 1.0,
    linucb_lambda: float = 1.0,
) -> Dict[str, Any]:
    final_strategies = strategies or ["random", "greedy", "adaptive", "contextual_linucb"]
    final_seeds = seeds or [11, 22, 33]
    chosen_model = model_path
    model_selection = None
    if not chosen_model:
        selected = select_best_training_model()
        if not selected:
            raise ValueError("No completed training run found. Provide model_path or train a model first.")
        chosen_model = str(selected["model_path"])
        model_selection = selected

    run_rows: List[Dict[str, Any]] = []
    for strategy in final_strategies:
        for seed in final_seeds:
            row = create_experiment_run(
                strategy=strategy,
                dataset_path=dataset_path,
                model_path=chosen_model,
                budget=int(budget),
                n_init=int(n_init),
                seed=int(seed),
                reward_mode=reward_mode,
                beta=float(beta),
                linucb_alpha=float(linucb_alpha),
                linucb_lambda=float(linucb_lambda),
            )
            run_rows.append(
                {
                    "run_id": row.get("id"),
                    "strategy": strategy,
                    "seed": seed,
                    "status": row.get("status"),
                    "summary": row.get("summary", {}),
                    "error_text": row.get("error_text"),
                }
            )

    by_strategy: Dict[str, List[Dict[str, Any]]] = {}
    for r in run_rows:
        by_strategy.setdefault(str(r.get("strategy")), []).append(r)

    aggregates: Dict[str, Dict[str, Any]] = {}
    for strategy, rows in by_strategy.items():
        completed = [r for r in rows if r.get("status") == "completed"]
        bests = [_safe_float((r.get("summary") or {}).get("best_yield"), default=0.0) for r in completed]
        steps = [_safe_float((r.get("summary") or {}).get("steps_completed"), default=0.0) for r in completed]
        hit_threshold = [1.0 if b >= 85.0 else 0.0 for b in bests]
        n = len(completed)
        aggregates[strategy] = {
            "runs_total": len(rows),
            "runs_completed": n,
            "best_yield_mean": (sum(bests) / n) if n else None,
            "best_yield_max": max(bests) if n else None,
            "avg_steps_completed": (sum(steps) / n) if n else None,
            "threshold_hit_rate_85": (sum(hit_threshold) / n) if n else None,
        }

    ranking = []
    for strategy, agg in aggregates.items():
        ranking.append(
            {
                "strategy": strategy,
                "best_yield_mean": agg.get("best_yield_mean"),
                "threshold_hit_rate_85": agg.get("threshold_hit_rate_85"),
            }
        )
    ranking.sort(key=lambda x: _safe_float(x.get("best_yield_mean"), default=-1.0), reverse=True)
    best_strategy = ranking[0]["strategy"] if ranking else None

    suite_payload = {
        "config": {
            "dataset_path": dataset_path,
            "model_path": chosen_model,
            "strategies": final_strategies,
            "seeds": final_seeds,
            "budget": int(budget),
            "n_init": int(n_init),
            "reward_mode": reward_mode,
            "beta": float(beta),
            "linucb_alpha": float(linucb_alpha),
            "linucb_lambda": float(linucb_lambda),
        },
        "model_selection": model_selection,
        "runs": run_rows,
        "aggregates": aggregates,
        "ranking": ranking,
        "selection_for_next_query": {
            "model_path": chosen_model,
            "strategy": best_strategy,
            "selection_policy": "max_mean_best_yield",
        },
        "created_at": now_iso(),
    }

    out = PROJECT_ROOT / "artifacts" / f"comparison_suite_{uuid.uuid4().hex[:8]}.json"
    out.write_text(json.dumps(suite_payload, indent=2), encoding="utf-8")
    suite_payload["artifact_path"] = str(out)
    return suite_payload


def get_latest_comparison_suite() -> Optional[Dict[str, Any]]:
    path = _latest_artifact("comparison_suite_*.json")
    if not path:
        return None
    return json.loads(path.read_text(encoding="utf-8"))

