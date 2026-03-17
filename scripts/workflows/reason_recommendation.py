from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen


def extract_json_object(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate human-facing reasoning for a ranked recommendation output."
    )
    parser.add_argument(
        "--recommendation-json",
        required=True,
        help="Path to JSON output from scripts/workflows/recommend_next.py.",
    )
    parser.add_argument(
        "--out-json",
        default="artifacts/recommendation_reasoning.json",
        help="Path to save reasoning payload.",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Attempt LLM-based explanation via Nebius/OpenAI-compatible endpoint.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Optional model override when using --use-llm.",
    )
    return parser.parse_args()


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def heuristic_reasoning(rec: Dict[str, Any]) -> Dict[str, Any]:
    ranked: List[Dict[str, Any]] = rec.get("ranked_candidates", [])
    if not ranked:
        raise ValueError("Recommendation JSON does not contain ranked_candidates.")

    top = ranked[0]
    top2 = ranked[1] if len(ranked) > 1 else None
    top_score = float(top["ucb_score"])
    gap = float(top_score - float(top2["ucb_score"])) if top2 else None

    uncertainty = float(top["predicted_uncertainty"])
    if uncertainty >= 12:
        confidence = "medium"
        caution = "Uncertainty is high; treat this as an informative probe with high upside."
    elif uncertainty >= 6:
        confidence = "medium-high"
        caution = "Moderate uncertainty; recommendation balances upside with useful information gain."
    else:
        confidence = "high"
        caution = "Lower uncertainty; recommendation is more exploitative and stable."

    why_now = (
        f"Top candidate has the strongest decision score (UCB={top_score:.2f}) from "
        f"predicted yield ({float(top['predicted_yield']):.2f}) plus exploration bonus "
        f"({float(top['explore_bonus']):.2f})."
    )
    if gap is not None:
        why_now += f" Score gap vs rank-2 is {gap:.2f}."

    next_rule = (
        "If observed yield is near or above predicted yield, exploit nearby conditions next; "
        "otherwise switch to rank-2 as fallback."
    )

    return {
        "mode": "heuristic",
        "confidence": confidence,
        "why_now": why_now,
        "caution_note": caution,
        "decision_rule_after_result": next_rule,
    }


def call_llm_reasoning(
    recommendation: Dict[str, Any],
    model_override: str = "",
) -> Dict[str, Any]:
    api_key = os.getenv("NEBIUS_API_KEY", "")
    base_url = os.getenv("NEBIUS_API_BASE", "https://api.studio.nebius.com/v1")
    model_name = model_override or os.getenv("NEBIUS_MODEL", "meta-llama/Meta-Llama-3.1-70B-Instruct")
    if not api_key:
        raise ValueError("NEBIUS_API_KEY is not set.")

    prompt = (
        "You are a scientific optimization assistant. Given a ranked set of candidate experiments, "
        "produce concise, human-facing explanation JSON with keys: "
        "confidence, why_now, caution_note, decision_rule_after_result. "
        "Keep each field short and actionable."
    )
    user_payload = {
        "next_experiment": recommendation.get("next_experiment"),
        "predicted_yield": recommendation.get("predicted_yield"),
        "predicted_uncertainty": recommendation.get("predicted_uncertainty"),
        "ranking_method": recommendation.get("ranking_method"),
        "beta": recommendation.get("beta"),
        "ranked_candidates": recommendation.get("ranked_candidates", [])[:3],
    }

    body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
        "temperature": 0.2,
    }
    data = json.dumps(body).encode("utf-8")
    req = Request(
        url=f"{base_url.rstrip('/')}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=60) as resp:
        response_json = json.loads(resp.read().decode("utf-8"))

    content = (
        response_json.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    parsed = extract_json_object(content)
    return {
        "mode": "llm",
        "model": model_name,
        **parsed,
    }


def main() -> None:
    args = parse_args()
    recommendation = load_json(args.recommendation_json)

    llm_error = None
    reasoning: Dict[str, Any]
    if args.use_llm:
        try:
            reasoning = call_llm_reasoning(recommendation, args.model)
        except (ValueError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as e:
            llm_error = str(e)
            reasoning = heuristic_reasoning(recommendation)
    else:
        reasoning = heuristic_reasoning(recommendation)

    output = {
        "next_experiment": recommendation.get("next_experiment"),
        "predicted_yield": recommendation.get("predicted_yield"),
        "predicted_uncertainty": recommendation.get("predicted_uncertainty"),
        "ranked_candidates": recommendation.get("ranked_candidates", [])[:3],
        "reasoning": reasoning,
        "llm_error": llm_error,
    }

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(json.dumps(output["reasoning"], indent=2))
    print(f"Saved reasoning payload: {out_path}")


if __name__ == "__main__":
    main()
