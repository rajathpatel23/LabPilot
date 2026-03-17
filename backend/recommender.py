"""
In-process recommendation + reasoning engine.

Replaces the subprocess calls to scripts/workflows/recommend_next.py and
scripts/workflows/reason_recommendation.py with direct function calls — eliminating
model reloading and process spawn overhead.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import joblib
import numpy as np
import pandas as pd

from modeling.io_utils import load_table
from modeling.surrogate import predict_with_uncertainty


# ---------------------------------------------------------------------------
# Model + data cache (avoids reloading on every request)
# ---------------------------------------------------------------------------

_model_cache: Dict[str, Any] = {}
_data_cache: Dict[str, pd.DataFrame] = {}


def _load_model(model_path: str) -> Dict[str, Any]:
    key = str(Path(model_path).resolve())
    if key not in _model_cache:
        _model_cache[key] = joblib.load(model_path)
    return _model_cache[key]


def _load_data(data_path: str) -> pd.DataFrame:
    key = str(Path(data_path).resolve())
    if key not in _data_cache:
        _data_cache[key] = load_table(data_path).reset_index(drop=True)
    return _data_cache[key].copy()


def invalidate_model_cache(model_path: str) -> None:
    """Call after retraining to drop stale model from cache."""
    key = str(Path(model_path).resolve())
    _model_cache.pop(key, None)


def invalidate_data_cache(data_path: str) -> None:
    key = str(Path(data_path).resolve())
    _data_cache.pop(key, None)


# ---------------------------------------------------------------------------
# Core recommendation (in-process, no subprocess)
# ---------------------------------------------------------------------------

def _json_safe(d: dict) -> dict:
    return {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in d.items()}


def recommend_next_inprocess(
    data_path: str,
    model_path: str,
    top_k: int = 5,
    beta: float = 0.8,
    exclude_indices: Optional[Set[int]] = None,
) -> Dict[str, Any]:
    """
    Fast in-process recommendation. Returns the same schema as
    scripts/workflows/recommend_next.py stdout.
    """
    bundle = _load_model(model_path)
    pipeline = bundle["pipeline"]
    feature_columns = bundle["feature_columns"]

    df = _load_data(data_path)
    exclude = exclude_indices or set()
    candidate_idx = [i for i in df.index if i not in exclude]
    if not candidate_idx:
        # Fallback: reset exclusion and pick from full pool
        candidate_idx = list(df.index)

    X = df.loc[candidate_idx, feature_columns]
    mean_pred, std_pred = predict_with_uncertainty(pipeline, X)
    scores = mean_pred + beta * std_pred

    ranked_df = (
        pd.DataFrame({
            "row_index": candidate_idx,
            "predicted_yield": mean_pred.values,
            "predicted_uncertainty": std_pred.values,
            "ucb_score": scores.values,
        })
        .sort_values("ucb_score", ascending=False)
        .head(max(1, top_k))
        .reset_index(drop=True)
    )

    ranked_candidates = []
    for rank_i, row in ranked_df.iterrows():
        idx = int(row["row_index"])
        params = _json_safe(df.loc[idx, feature_columns].to_dict())
        ranked_candidates.append({
            "rank": int(rank_i + 1),
            "row_index": idx,
            "params": params,
            "conditions": params,
            "predicted_yield": float(row["predicted_yield"]),
            "predicted_uncertainty": float(row["predicted_uncertainty"]),
            "exploit_score": float(row["predicted_yield"]),
            "explore_bonus": float(beta * row["predicted_uncertainty"]),
            "ucb_score": float(row["ucb_score"]),
            "reasoning": "Ranked by UCB = predicted_yield + β·uncertainty.",
        })

    best = ranked_candidates[0]
    best_idx = int(ranked_df.loc[0, "row_index"])
    best_row = _json_safe(df.loc[best_idx, feature_columns].to_dict())

    return {
        "next_experiment": best_row,
        "predicted_yield": best["predicted_yield"],
        "predicted_uncertainty": best["predicted_uncertainty"],
        "ranking_method": "ucb",
        "beta": beta,
        "row_index": best["row_index"],
        "ranked_candidates": ranked_candidates,
        "top_candidates": ranked_candidates,
    }


# ---------------------------------------------------------------------------
# Heuristic reasoning (in-process, no subprocess)
# ---------------------------------------------------------------------------

def heuristic_reasoning(rec: Dict[str, Any]) -> Dict[str, Any]:
    ranked = rec.get("ranked_candidates") or []
    if not ranked:
        return {
            "mode": "heuristic",
            "confidence": "low",
            "why_now": "No ranked candidates available.",
            "caution_note": "Recommendation may be unreliable.",
            "decision_rule_after_result": "Collect more data before trusting suggestions.",
        }

    top = ranked[0]
    top2 = ranked[1] if len(ranked) > 1 else None
    top_score = float(top.get("ucb_score", 0))
    gap = float(top_score - float(top2["ucb_score"])) if top2 else None

    uncertainty = float(top.get("predicted_uncertainty", 0))
    if uncertainty >= 12:
        confidence = "medium"
        caution = "High uncertainty — treat as an informative probe with high upside."
    elif uncertainty >= 6:
        confidence = "medium-high"
        caution = "Moderate uncertainty — balances upside with useful information gain."
    else:
        confidence = "high"
        caution = "Low uncertainty — recommendation is exploitative and stable."

    why = (
        f"Top candidate scores UCB {top_score:.1f} "
        f"(yield {float(top.get('predicted_yield', 0)):.1f} + exploration {float(top.get('explore_bonus', 0)):.1f})."
    )
    if gap is not None:
        why += f" Gap vs #2: {gap:.1f}."

    return {
        "mode": "heuristic",
        "confidence": confidence,
        "why_now": why,
        "caution_note": caution,
        "decision_rule_after_result": (
            "If observed yield ≥ predicted, exploit nearby conditions; "
            "otherwise try rank-2 as a contrast experiment."
        ),
    }


# ---------------------------------------------------------------------------
# Optional LLM reasoning
# ---------------------------------------------------------------------------

def llm_reasoning(
    rec: Dict[str, Any],
    model_override: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_question: Optional[str] = None,
) -> Dict[str, Any]:
    api_key = os.getenv("NEBIUS_API_KEY", "")
    base_url = os.getenv("NEBIUS_API_BASE", "https://api.studio.nebius.com/v1")
    model_name = model_override or os.getenv("NEBIUS_MODEL", "meta-llama/Meta-Llama-3.1-70B-Instruct")
    if not api_key:
        raise ValueError("NEBIUS_API_KEY is not set.")

    # Build system prompt with context awareness
    base_prompt = (
        "You are a scientific optimization assistant. Given ranked experiment candidates, "
        "produce a concise JSON with keys: confidence, why_now, caution_note, decision_rule_after_result. "
        "Keep each value ≤2 sentences."
    )
    
    # Add conversation context if available
    context_note = ""
    if conversation_history and len(conversation_history) > 0:
        context_note += "\n\nIMPORTANT: You have access to the conversation history below. "
        context_note += "If the user is asking a follow-up question (e.g., 'tell me more', 'why did you recommend that', 'what about X'), "
        context_note += "use the conversation context to provide a relevant, context-aware answer. "
        context_note += "Reference previous recommendations, conditions, or discussions when relevant.\n"
        
        recent = conversation_history[-6:]  # Last 6 messages for better context
        context_parts = []
        for msg in recent:
            role = msg.get("role", "")
            content = str(msg.get("content", ""))
            if role == "user":
                context_parts.append(f"User: {content[:300]}")
            elif role == "assistant":
                # Include key info from assistant messages
                content_short = content[:250]
                context_parts.append(f"Assistant: {content_short}...")
        if context_parts:
            context_note += "\nConversation history:\n" + "\n".join(context_parts)
    
    if user_question:
        context_note += f"\n\nUser's current question/request: {user_question}"
        context_note += "\n\nIf this is a follow-up question, make sure your reasoning addresses what the user is asking about."
    
    prompt = base_prompt + context_note
    
    payload = {
        "next_experiment": rec.get("next_experiment"),
        "predicted_yield": rec.get("predicted_yield"),
        "predicted_uncertainty": rec.get("predicted_uncertainty"),
        "ranked_candidates": (rec.get("ranked_candidates") or [])[:3],
    }
    
    # Build messages array - include conversation history as prior messages, then current payload
    messages = [{"role": "system", "content": prompt}]
    
    # Add conversation history as prior turns (helps LLM understand context)
    if conversation_history:
        for msg in conversation_history[-8:]:  # Last 8 messages for full context
            role = msg.get("role", "")
            content = str(msg.get("content", ""))
            if role in ("user", "assistant") and content.strip():
                # Truncate very long messages to stay within token limits
                content_clean = content[:400].strip()
                if content_clean:
                    messages.append({"role": role, "content": content_clean})
    
    # Add current recommendation payload as the final user message
    payload_text = json.dumps(payload, indent=2)
    messages.append({"role": "user", "content": f"Current recommendation data:\n{payload_text}"})
    
    body = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 400,  # Increased for context-aware responses
    }
    req = Request(
        url=f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    choices = data.get("choices") or [{}]
    message = (choices[0] if choices else {}).get("message") or {}
    raw_content = message.get("content")
    text = (raw_content or "").strip()
    if not text:
        raise ValueError("LLM returned empty content.")
    # Parse JSON from possible markdown wrapping
    cleaned = text
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").replace("json\n", "", 1).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        s, e = cleaned.find("{"), cleaned.rfind("}")
        if s != -1 and e > s:
            parsed = json.loads(cleaned[s:e+1])
        else:
            raise
    return {"mode": "llm", "model": model_name, **parsed}


# ---------------------------------------------------------------------------
# Combined: recommend + reason (single call, no subprocess)
# ---------------------------------------------------------------------------

def recommend_with_reasoning(
    data_path: str,
    model_path: str,
    top_k: int = 5,
    beta: float = 0.8,
    use_llm: bool = False,
    exclude_indices: Optional[Set[int]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_question: Optional[str] = None,
) -> Dict[str, Any]:
    """
    One-shot: recommend + reason, all in-process.
    Returns {recommendation, reasoning, llm_error}.
    
    Args:
        conversation_history: List of previous messages in format [{"role": "user|assistant", "content": "..."}, ...]
        user_question: The current user's question/request for context-aware reasoning
    """
    rec = recommend_next_inprocess(
        data_path=data_path,
        model_path=model_path,
        top_k=top_k,
        beta=beta,
        exclude_indices=exclude_indices,
    )

    llm_error = None
    if use_llm:
        try:
            reasoning = llm_reasoning(rec, conversation_history=conversation_history, user_question=user_question)
        except (ValueError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as e:
            llm_error = str(e)
            reasoning = heuristic_reasoning(rec)
    else:
        reasoning = heuristic_reasoning(rec)

    return {
        "recommendation": rec,
        "reasoning": reasoning,
        "llm_error": llm_error,
    }


# ---------------------------------------------------------------------------
# Structured assistant text builder
# ---------------------------------------------------------------------------

def format_assistant_text(
    rec: Dict[str, Any],
    reasoning: Dict[str, Any],
    evidence: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a clean, section-separated assistant message."""
    next_exp = rec.get("next_experiment") or {}
    pred = rec.get("predicted_yield")
    unc = rec.get("predicted_uncertainty")

    # Condition summary
    preferred = [
        "Catalyst_1_Short_Hand", "Ligand_Short_Hand", "Solvent_1_Short_Hand",
        "Reagent_1_Short_Hand", "catalyst", "ligand", "solvent", "base",
    ]
    parts = []
    for k in preferred:
        v = next_exp.get(k)
        if v is not None:
            label = k.replace("_Short_Hand", "").replace("_1", "").replace("_", " ")
            parts.append(f"{label}: {v}")
        if len(parts) >= 4:
            break
    cond_text = ", ".join(parts) if parts else "top-ranked candidate"

    lines = []
    lines.append(f"**Recommendation:** {cond_text}")
    if pred is not None:
        yield_str = f"{float(pred):.1f}%"
        if unc is not None:
            yield_str += f" (±{float(unc):.1f})"
        lines.append(f"**Predicted yield:** {yield_str}")

    why = reasoning.get("why_now", "Balances payoff and information gain.")
    lines.append(f"**Why now:** {why}")

    caution = reasoning.get("caution_note") or reasoning.get("cautionary_note")
    if caution:
        lines.append(f"**Caution:** {caution}")

    follow = reasoning.get("decision_rule_after_result")
    if follow:
        lines.append(f"**Next step:** {follow}")

    # Evidence summary if present
    if evidence and evidence.get("status") == "ok":
        answer = evidence.get("answer")
        if answer:
            lines.append(f"**Literature insight:** {answer[:300]}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# General-purpose LLM responder (handles all question types)
# ---------------------------------------------------------------------------

def llm_general_response(
    user_question: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    recommendation_context: Optional[Dict[str, Any]] = None,
    literature_context: Optional[Dict[str, Any]] = None,
    model_override: str = "",
) -> Dict[str, Any]:
    """
    General-purpose LLM responder that can answer any question with full context.
    Uses conversation history, recent recommendations, and literature to provide comprehensive answers.
    
    Returns: {
        "response": str,  # Natural language answer
        "sources": List[str],  # What context was used
        "needs_recommendation": bool,  # Whether to trigger recommendation
        "needs_literature": bool,  # Whether to trigger literature search
    }
    """
    api_key = os.getenv("NEBIUS_API_KEY", "")
    base_url = os.getenv("NEBIUS_API_BASE", "https://api.studio.nebius.com/v1")
    model_name = model_override or os.getenv("NEBIUS_MODEL", "meta-llama/Meta-Llama-3.1-70B-Instruct")
    if not api_key:
        raise ValueError("NEBIUS_API_KEY is not set.")

    # Build comprehensive system prompt
    system_parts = [
        "You are LabPilot, an AI copilot for experiment optimization in R&D labs.",
        "You help scientists decide the next best experiment by combining:",
        "- Surrogate models trained on historical data",
        "- Adaptive optimization strategies (UCB, contextual bandits)",
        "- Literature evidence from JACS, Chemical Science, and other journals",
        "",
        "You have access to:",
        "1. Conversation history (previous questions and recommendations)",
        "2. Recent experiment recommendations (if available)",
        "3. Literature search results (if available)",
        "",
        "Your task: Answer the user's question comprehensively using all available context.",
        "If the question requires a new recommendation, say so clearly.",
        "If the question is about literature, use any available literature context.",
        "Be helpful, accurate, and reference specific details when available.",
        "If you don't have enough information, suggest what would help.",
    ]
    
    # Build context summary
    context_summary = []
    sources = []
    
    if conversation_history and len(conversation_history) > 0:
        recent = conversation_history[-6:]
        context_summary.append("\n=== Recent Conversation ===")
        for msg in recent:
            role = msg.get("role", "")
            content = str(msg.get("content", ""))[:300]
            if role == "user":
                context_summary.append(f"User: {content}")
            elif role == "assistant":
                context_summary.append(f"Assistant: {content[:250]}...")
        sources.append("conversation_history")
    
    if recommendation_context:
        rec = recommendation_context
        next_exp = rec.get("next_experiment", {}) or {}
        ranked = rec.get("ranked_candidates", []) or rec.get("top_candidates", []) or []
        
        context_summary.append("\n=== Current Recommendation Data ===")
        
        # Format top candidate conditions nicely
        if next_exp:
            cond_parts = []
            preferred_keys = ["Catalyst_1_Short_Hand", "Ligand_Short_Hand", "Solvent_1_Short_Hand", 
                             "Reagent_1_Short_Hand", "Reactant_1_Short_Hand", "Reactant_2_Name"]
            for key in preferred_keys:
                val = next_exp.get(key)
                if val is not None:
                    label = key.replace("_Short_Hand", "").replace("_1", "").replace("_", " ")
                    cond_parts.append(f"{label}: {val}")
            if cond_parts:
                context_summary.append(f"Top recommended conditions: {', '.join(cond_parts[:4])}")
        
        if rec.get("predicted_yield") is not None:
            yield_val = rec.get("predicted_yield")
            unc_val = rec.get("predicted_uncertainty")
            if unc_val is not None:
                context_summary.append(f"Predicted yield: {yield_val:.1f}% (±{unc_val:.1f})")
            else:
                context_summary.append(f"Predicted yield: {yield_val:.1f}%")
        
        if ranked:
            context_summary.append(f"\nTop {min(len(ranked), 3)} ranked candidates:")
            for i, cand in enumerate(ranked[:3], 1):
                cand_exp = cand.get("conditions") or cand.get("params") or {}
                cand_yield = cand.get("predicted_yield")
                cand_rank = cand.get("rank", i)
                cond_str = ", ".join([f"{k}: {v}" for k, v in list(cand_exp.items())[:3]])
                if cand_yield is not None:
                    context_summary.append(f"  Rank {cand_rank}: {cond_str} (yield: {cand_yield:.1f}%)")
                else:
                    context_summary.append(f"  Rank {cand_rank}: {cond_str}")
        
        sources.append("recommendation")
    
    if literature_context:
        lit = literature_context
        context_summary.append("\n=== Literature Search Results ===")
        
        # Paper summary
        if lit.get("paper_summary"):
            context_summary.append(f"Summary: {lit.get('paper_summary')}")
        
        # Evidence results with details
        evidence = lit.get("evidence", {}) or {}
        results = evidence.get("results", []) or []
        if results:
            context_summary.append(f"\nFound {len(results)} relevant papers:")
            for i, paper in enumerate(results[:5], 1):
                title = paper.get("title", "Untitled")
                snippet = paper.get("snippet", "")[:200]
                url = paper.get("url", "")
                context_summary.append(f"  {i}. {title}")
                if snippet:
                    context_summary.append(f"     {snippet}...")
                if url:
                    context_summary.append(f"     URL: {url}")
        
        # Relevance information
        relevance = lit.get("relevance", {}) or {}
        if relevance:
            level = relevance.get("level", "medium")
            why_related = relevance.get("why_related", []) or []
            context_summary.append(f"\nRelevance level: {level}")
            if why_related:
                context_summary.append(f"Why related: {'; '.join(str(x) for x in why_related[:3])}")
        
        sources.append("literature")
    
    context_text = "\n".join(context_summary) if context_summary else "No additional context available."
    
    system_prompt = "\n".join(system_parts) + "\n\n" + context_text
    
    # Build messages array
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation history as prior messages (full context)
    if conversation_history:
        for msg in conversation_history[-12:]:  # Increased to 12 for more context
            role = msg.get("role", "")
            content = str(msg.get("content", ""))
            if role in ("user", "assistant") and content.strip():
                # Include full message content, truncate only if extremely long
                content_clean = content[:600].strip()
                if content_clean:
                    messages.append({"role": role, "content": content_clean})
    
    # Add current question with emphasis
    messages.append({
        "role": "user", 
        "content": f"User's current question: {user_question}\n\nPlease answer this question using all the context provided above, including conversation history, recommendations, and literature."
    })
    
    body = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.7,  # Higher for more natural responses
        "max_tokens": 600,  # Longer responses for comprehensive answers
    }
    
    req = Request(
        url=f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    
    try:
        with urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode())
        choices = data.get("choices") or [{}]
        message = (choices[0] if choices else {}).get("message") or {}
        response_text = (message.get("content") or "").strip()

        # If the LLM returns an empty response, fall back to a safe, context-based summary
        if not response_text:
            fallback_lines = ["Based on the current context:"]
            if recommendation_context:
                fallback_lines.append(
                    " - I considered the latest recommended conditions and their predicted yield/uncertainty."
                )
            if literature_context:
                fallback_lines.append(
                    " - I used the retrieved literature snippets and relevance assessment."
                )
            if conversation_history:
                fallback_lines.append(
                    " - I looked at your recent questions and previous assistant responses in this thread."
                )
            fallback_lines.append(
                "However, the reasoning model did not return a detailed narrative. "
                "You can still run the recommended experiment and, if needed, ask a more specific follow-up question "
                "about conditions, trade-offs, or evidence."
            )
            response_text = "\n".join(fallback_lines)

        # Determine if we need to trigger tools
        needs_recommendation = any(
            kw in user_question.lower()
            for kw in ["recommend", "suggest", "next experiment", "what should", "what to try"]
        )
        needs_literature = any(
            kw in user_question.lower()
            for kw in ["literature", "paper", "citation", "jacs", "chemical science", "published", "evidence"]
        )

        return {
            "response": response_text,
            "sources": sources,
            "needs_recommendation": needs_recommendation,
            "needs_literature": needs_literature,
            "model": model_name,
        }
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        # Silent fallback: do not surface internal errors to the user, just provide a generic,
        # context-based answer so the chat never shows a scary error string.
        fallback_lines = ["I'm using the available context to respond, but the reasoning model had trouble generating a detailed answer."]
        if recommendation_context:
            fallback_lines.append(
                " - You can trust the ranked candidates and predicted yields shown; they come from the surrogate model and policy."
            )
        if literature_context:
            fallback_lines.append(
                " - The listed papers and snippets are still valid evidence; consider them when deciding your next experiment."
            )
        fallback_lines.append(
            "If you want a deeper explanation, try asking a more targeted question (for example, "
            "\"why this catalyst vs the runner-up?\" or \"how does the literature support this solvent choice?\")."
        )
        return {
            "response": "\n".join(fallback_lines),
            "sources": sources,
            "needs_recommendation": False,
            "needs_literature": False,
            "error": "llm_general_response_fallback",
        }
