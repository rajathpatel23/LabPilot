"""
In-process recommendation + reasoning engine.

Replaces the subprocess calls to recommend_next.py and reason_recommendation.py
with direct function calls — eliminates model reloading and process spawn overhead.
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
    Fast in-process recommendation.  Returns the same schema as recommend_next.py stdout.
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

def llm_reasoning(rec: Dict[str, Any], model_override: str = "") -> Dict[str, Any]:
    api_key = os.getenv("NEBIUS_API_KEY", "")
    base_url = os.getenv("NEBIUS_API_BASE", "https://api.studio.nebius.com/v1")
    model_name = model_override or os.getenv("NEBIUS_MODEL", "meta-llama/Meta-Llama-3.1-70B-Instruct")
    if not api_key:
        raise ValueError("NEBIUS_API_KEY is not set.")

    prompt = (
        "You are a scientific optimization assistant. Given ranked experiment candidates, "
        "produce a concise JSON with keys: confidence, why_now, caution_note, decision_rule_after_result. "
        "Keep each value ≤2 sentences."
    )
    payload = {
        "next_experiment": rec.get("next_experiment"),
        "predicted_yield": rec.get("predicted_yield"),
        "predicted_uncertainty": rec.get("predicted_uncertainty"),
        "ranked_candidates": (rec.get("ranked_candidates") or [])[:3],
    }
    body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload)},
        ],
        "temperature": 0.2,
        "max_tokens": 300,
    }
    req = Request(
        url=f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
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
) -> Dict[str, Any]:
    """
    One-shot: recommend + reason, all in-process.
    Returns {recommendation, reasoning, llm_error}.
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
            reasoning = llm_reasoning(rec)
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
