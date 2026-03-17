from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
RECOMMEND_SCRIPT = REPO_ROOT / "scripts" / "workflows" / "recommend_next.py"
REASON_SCRIPT = REPO_ROOT / "scripts" / "workflows" / "reason_recommendation.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an end-to-end agentic orchestration showcase for LabPilot."
    )
    parser.add_argument("--data", required=True, help="Dataset path (.csv or .xlsx).")
    parser.add_argument("--model", required=True, help="Trained surrogate model path.")
    parser.add_argument("--top-k", type=int, default=5, help="Candidate list size.")
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use LLM explanation path in scripts/workflows/reason_recommendation.py (requires env key).",
    )
    parser.add_argument(
        "--use-tavily",
        action="store_true",
        help="Use Tavily search for lightweight literature guardrails (requires TAVILY_API_KEY).",
    )
    parser.add_argument(
        "--out-json",
        default="artifacts/agentic_showcase_output.json",
        help="Output JSON path.",
    )
    return parser.parse_args()


def run_json_cmd(cmd: List[str]) -> Dict[str, Any]:
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(proc.stdout.strip())


def run_cmd(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True)


def call_tavily_guardrail(query: str) -> Dict[str, Any]:
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise ValueError("TAVILY_API_KEY is not set.")

    body = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": 3,
        "include_answer": False,
    }
    req = Request(
        url="https://api.tavily.com/search",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload


def heuristic_guardrail_from_candidates(recommendation: Dict[str, Any]) -> Dict[str, Any]:
    ranked = recommendation.get("ranked_candidates", [])
    if not ranked:
        return {"status": "warning", "notes": ["No candidates available to guardrail."]}

    top = ranked[0]
    uncertainty = float(top.get("predicted_uncertainty", 0.0))
    notes = []
    if uncertainty > 12:
        notes.append("High uncertainty: run as informative probe with fallback prepared.")
    elif uncertainty > 6:
        notes.append("Moderate uncertainty: balanced exploitation/exploration.")
    else:
        notes.append("Lower uncertainty: recommendation is relatively stable.")

    if len(ranked) > 1:
        gap = float(top["ucb_score"]) - float(ranked[1]["ucb_score"])
        if gap < 0.5:
            notes.append("Top-1 vs Top-2 score gap is small; keep rank-2 as active backup.")

    return {
        "status": "ok",
        "notes": notes,
        "top_candidate_score": float(top["ucb_score"]),
    }


def main() -> None:
    args = parse_args()
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    trace: List[Dict[str, Any]] = []

    # Tool 1: Optimization / ranking tool.
    rec_cmd = [
        sys.executable,
        str(RECOMMEND_SCRIPT),
        "--data",
        args.data,
        "--model",
        args.model,
        "--top-k",
        str(args.top_k),
    ]
    recommendation = run_json_cmd(rec_cmd)
    trace.append(
        {
            "tool": "optimizer.recommend_next",
            "status": "ok",
            "details": {
                "top_k": args.top_k,
                "ranking_method": recommendation.get("ranking_method"),
                "row_index": recommendation.get("row_index"),
            },
        }
    )

    # Tool 2: Guardrails tool (heuristic always, Tavily optional).
    guardrail = {
        "heuristic": heuristic_guardrail_from_candidates(recommendation),
        "tavily": None,
        "tavily_error": None,
    }
    if args.use_tavily:
        top = recommendation.get("next_experiment", {})
        query = (
            "Suzuki-Miyaura reaction condition plausibility "
            f"ligand {top.get('Ligand_Short_Hand', '')} "
            f"base/reagent {top.get('Reagent_1_Short_Hand', '')} "
            f"solvent {top.get('Solvent_1_Short_Hand', '')}"
        )
        try:
            tavily_payload = call_tavily_guardrail(query)
            guardrail["tavily"] = {
                "query": query,
                "results": tavily_payload.get("results", [])[:3],
            }
            trace.append({"tool": "guardrail.tavily", "status": "ok"})
        except (ValueError, HTTPError, URLError, TimeoutError) as e:
            guardrail["tavily_error"] = str(e)
            trace.append({"tool": "guardrail.tavily", "status": "fallback", "error": str(e)})
    else:
        trace.append({"tool": "guardrail.heuristic", "status": "ok"})

    # Tool 3: Reasoning tool.
    tmp_rec = out_path.parent / "_tmp_recommendation.json"
    with tmp_rec.open("w", encoding="utf-8") as f:
        json.dump(recommendation, f, indent=2)

    reason_cmd = [
        sys.executable,
        str(REASON_SCRIPT),
        "--recommendation-json",
        str(tmp_rec),
        "--out-json",
        str(out_path.parent / "_tmp_reasoning.json"),
    ]
    if args.use_llm:
        reason_cmd.append("--use-llm")

    run_cmd(reason_cmd)
    with (out_path.parent / "_tmp_reasoning.json").open("r", encoding="utf-8") as f:
        reasoning_out = json.load(f)
    trace.append(
        {
            "tool": "reasoning.explainer",
            "status": "ok",
            "mode": reasoning_out.get("reasoning", {}).get("mode", "heuristic"),
        }
    )

    final_payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "agent_mode": "labpilot_showcase",
        "tools_used": [
            "optimizer.recommend_next",
            "guardrail.heuristic",
            "guardrail.tavily" if args.use_tavily else None,
            "reasoning.explainer",
        ],
        "recommendation": recommendation,
        "guardrail": guardrail,
        "reasoning": reasoning_out.get("reasoning", {}),
        "agent_trace": trace,
    }
    final_payload["tools_used"] = [t for t in final_payload["tools_used"] if t]

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2)

    print(json.dumps({"saved": str(out_path), "tools_used": final_payload["tools_used"]}, indent=2))


if __name__ == "__main__":
    main()
