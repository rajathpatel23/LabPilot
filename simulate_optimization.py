from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import joblib
import numpy as np

from modeling.bandit_policy import LinearUCBBandit, UCB1Bandit
from modeling.io_utils import load_table
from modeling.surrogate import predict_with_uncertainty


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run optimization loop simulation.")
    parser.add_argument("--data", required=True, help="Path to dataset (.csv or .xlsx).")
    parser.add_argument("--model", required=True, help="Path to trained model joblib.")
    parser.add_argument("--budget", type=int, default=20, help="Experiment budget.")
    parser.add_argument("--n-init", type=int, default=3, help="Initial random observations.")
    parser.add_argument(
        "--strategy",
        choices=["random", "adaptive", "bandit_ucb", "contextual_linucb"],
        default="adaptive",
        help="Simulation strategy.",
    )
    parser.add_argument("--beta", type=float, default=0.8, help="UCB exploration weight.")
    parser.add_argument(
        "--bandit-c",
        type=float,
        default=1.0,
        help="Exploration coefficient for explicit UCB1 bandit strategy.",
    )
    parser.add_argument(
        "--reward-mode",
        choices=["yield", "improvement"],
        default="yield",
        help="Reward shaping mode for bandit updates.",
    )
    parser.add_argument(
        "--linucb-alpha",
        type=float,
        default=1.0,
        help="Exploration coefficient for contextual LinUCB strategy.",
    )
    parser.add_argument(
        "--linucb-lambda",
        type=float,
        default=1.0,
        help="L2 regularization term for contextual LinUCB strategy.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--out",
        default="artifacts/simulation_results.json",
        help="Output path for simulation results.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed)

    bundle = joblib.load(args.model)
    pipeline = bundle["pipeline"]
    feature_columns = bundle["feature_columns"]
    target_column = bundle["target_column"]

    df = load_table(args.data).reset_index(drop=True)
    if target_column not in df.columns:
        raise ValueError(f"Target column '{target_column}' not found in dataset.")

    if len(df) < max(args.budget, args.n_init):
        raise ValueError("Dataset has fewer rows than required budget/init size.")

    all_indices = list(df.index)
    observed = set(rng.choice(all_indices, size=args.n_init, replace=False).tolist())
    bandit = UCB1Bandit(c=args.bandit_c)
    linucb = None
    context_lookup = {}
    if args.strategy == "contextual_linucb":
        preprocessor = pipeline.named_steps["preprocessor"]
        X_all = df[feature_columns]
        X_all_context = preprocessor.transform(X_all)
        dense_context = np.asarray(X_all_context.toarray() if hasattr(X_all_context, "toarray") else X_all_context)
        context_lookup = {int(idx): dense_context[int(idx)] for idx in all_indices}
        linucb = LinearUCBBandit(
            dim=dense_context.shape[1],
            alpha=args.linucb_alpha,
            lambda_reg=args.linucb_lambda,
        )

    history = []
    best_so_far = -float("inf")

    # Record initial observations
    for idx in sorted(observed):
        y = float(df.loc[idx, target_column])
        reward = y
        if args.reward_mode == "improvement":
            reward = y - best_so_far if best_so_far > -float("inf") else y
        best_so_far = max(best_so_far, y)
        bandit.update(int(idx), float(reward))
        if linucb is not None:
            linucb.update(context_lookup[int(idx)], float(reward))
        history.append(
            {
                "step": len(history) + 1,
                "index": int(idx),
                "strategy": "init",
                "observed_yield": y,
                "reward": float(reward),
                "best_so_far": best_so_far,
            }
        )

    while len(history) < args.budget:
        candidate_indices = [idx for idx in all_indices if idx not in observed]
        if not candidate_indices:
            break

        if args.strategy == "random":
            chosen_idx = int(rng.choice(candidate_indices))
            pred_mean = None
            pred_std = None
            strategy_score = None
        else:
            if args.strategy == "adaptive":
                X_candidates = df.loc[candidate_indices, feature_columns]
                mean_pred, std_pred = predict_with_uncertainty(pipeline, X_candidates)
                scores = mean_pred + args.beta * std_pred
                best_pos = int(np.argmax(scores.values))
                chosen_idx = int(candidate_indices[best_pos])
                pred_mean = float(mean_pred.iloc[best_pos])
                pred_std = float(std_pred.iloc[best_pos])
                strategy_score = float(scores.iloc[best_pos])
            elif args.strategy == "contextual_linucb":
                if linucb is None:
                    raise ValueError("LinUCB strategy selected but contextual bandit was not initialized.")
                chosen_idx, strategy_score = linucb.select(candidate_indices, context_lookup)
                pred_mean = None
                pred_std = None
            else:
                chosen_idx, strategy_score = bandit.select(candidate_indices)
                pred_mean = None
                pred_std = None

        observed.add(chosen_idx)
        y_obs = float(df.loc[chosen_idx, target_column])
        reward = y_obs
        if args.reward_mode == "improvement":
            reward = y_obs - best_so_far
        best_so_far = max(best_so_far, y_obs)
        bandit.update(chosen_idx, float(reward))
        if linucb is not None:
            linucb.update(context_lookup[chosen_idx], float(reward))

        history.append(
            {
                "step": len(history) + 1,
                "index": chosen_idx,
                "strategy": args.strategy,
                "predicted_yield": pred_mean,
                "predicted_uncertainty": pred_std,
                "strategy_score": (
                    float(strategy_score)
                    if strategy_score is not None and math.isfinite(strategy_score)
                    else None
                ),
                "observed_yield": y_obs,
                "reward": float(reward),
                "best_so_far": best_so_far,
            }
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "strategy": args.strategy,
        "budget": args.budget,
        "n_init": args.n_init,
        "reward_mode": args.reward_mode,
        "steps_completed": len(history),
        "best_yield": max(item["best_so_far"] for item in history) if history else None,
        "history": history,
    }

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"Simulation completed: {len(history)} steps")
    print(f"Best yield found: {payload['best_yield']}")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

