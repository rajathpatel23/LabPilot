from __future__ import annotations

import argparse
import json

import joblib
import pandas as pd

from modeling.io_utils import load_table
from modeling.surrogate import predict_with_uncertainty


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recommend next experiment.")
    parser.add_argument("--data", required=True, help="Path to dataset (.csv or .xlsx).")
    parser.add_argument("--model", required=True, help="Path to trained model joblib.")
    parser.add_argument(
        "--history",
        default="",
        help="Optional CSV with tried experiment indices (column: index).",
    )
    parser.add_argument("--beta", type=float, default=0.8, help="UCB exploration weight.")
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of ranked candidate experiments to return.",
    )
    return parser.parse_args()


def load_tried_indices(history_path: str) -> set[int]:
    if not history_path:
        return set()
    history_df = pd.read_csv(history_path)
    if "index" not in history_df.columns:
        raise ValueError("History CSV must contain an 'index' column.")
    return set(history_df["index"].astype(int).tolist())


def json_safe_row(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        out[k] = None if pd.isna(v) else v
    return out


def main() -> None:
    args = parse_args()
    bundle = joblib.load(args.model)
    pipeline = bundle["pipeline"]
    feature_columns = bundle["feature_columns"]

    df = load_table(args.data).reset_index(drop=True)
    tried_indices = load_tried_indices(args.history)

    candidate_indices = [idx for idx in df.index if idx not in tried_indices]
    if not candidate_indices:
        raise ValueError("No candidates left. All rows are already in history.")

    X_candidates = df.loc[candidate_indices, feature_columns]
    mean_pred, std_pred = predict_with_uncertainty(pipeline, X_candidates)
    scores = mean_pred + args.beta * std_pred

    ranked = (
        pd.DataFrame(
            {
                "row_index": candidate_indices,
                "predicted_yield": mean_pred.values,
                "predicted_uncertainty": std_pred.values,
                "ucb_score": scores.values,
            }
        )
        .sort_values("ucb_score", ascending=False)
        .reset_index(drop=True)
    )
    ranked = ranked.head(max(1, args.top_k))

    best_pos = 0
    best_idx = int(ranked.loc[best_pos, "row_index"])
    best_row = json_safe_row(df.loc[best_idx, feature_columns].to_dict())

    ranked_candidates = []
    for rank, rec in ranked.iterrows():
        idx = int(rec["row_index"])
        params = json_safe_row(df.loc[idx, feature_columns].to_dict())
        ranked_candidates.append(
            {
                "rank": int(rank + 1),
                "row_index": idx,
                "params": params,
                "predicted_yield": float(rec["predicted_yield"]),
                "predicted_uncertainty": float(rec["predicted_uncertainty"]),
                "exploit_score": float(rec["predicted_yield"]),
                "explore_bonus": float(args.beta * rec["predicted_uncertainty"]),
                "ucb_score": float(rec["ucb_score"]),
                "reasoning": (
                    "Ranked by UCB = predicted_yield + beta * uncertainty. "
                    "Higher yield favors exploitation; higher uncertainty favors exploration."
                ),
            }
        )

    best = ranked_candidates[0]

    result = {
        "next_experiment": best_row,
        "predicted_yield": best["predicted_yield"],
        "predicted_uncertainty": best["predicted_uncertainty"],
        "rationale_stub": (
            "Top candidate selected by UCB ranking that balances high predicted yield "
            "with informative uncertainty."
        ),
        "row_index": best["row_index"],
        "ranking_method": "ucb",
        "beta": args.beta,
        "ranked_candidates": ranked_candidates,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

