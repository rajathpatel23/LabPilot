from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_SYSTEM_PROMPT = (
    "You are a scientific optimization assistant for R&D experiment planning. "
    "Given ranked candidate experiments and score decomposition, return concise JSON with keys: "
    "confidence, why_now, caution_note, decision_rule_after_result, backup_option_note."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build LLM-ready input payload from recommendation JSON."
    )
    parser.add_argument(
        "--recommendation-json",
        required=True,
        help="Path to JSON output from recommend_next.py.",
    )
    parser.add_argument(
        "--out-json",
        default="artifacts/llm_input.json",
        help="Output path for payload to send to LLM endpoint.",
    )
    parser.add_argument(
        "--system-prompt-file",
        default="prompts/recommendation_reasoning_prompt.md",
        help="Optional file path to read system prompt text from.",
    )
    parser.add_argument(
        "--evidence-json",
        default="",
        help="Optional JSON file with guardrail/literature evidence to include as optional_evidence.",
    )
    return parser.parse_args()


def load_system_prompt(path: str) -> str:
    p = Path(path)
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return DEFAULT_SYSTEM_PROMPT


def main() -> None:
    args = parse_args()
    with open(args.recommendation_json, "r", encoding="utf-8") as f:
        rec: Dict[str, Any] = json.load(f)

    user_payload = {
        "next_experiment": rec.get("next_experiment"),
        "predicted_yield": rec.get("predicted_yield"),
        "predicted_uncertainty": rec.get("predicted_uncertainty"),
        "ranking_method": rec.get("ranking_method"),
        "beta": rec.get("beta"),
        "ranked_candidates": rec.get("ranked_candidates", [])[:3],
    }
    if args.evidence_json:
        with open(args.evidence_json, "r", encoding="utf-8") as f:
            user_payload["optional_evidence"] = json.load(f)

    system_prompt = load_system_prompt(args.system_prompt_file)

    chat_payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
        "temperature": 0.2,
    }

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(chat_payload, f, indent=2)

    print(f"Saved LLM input payload: {out_path}")


if __name__ == "__main__":
    main()

