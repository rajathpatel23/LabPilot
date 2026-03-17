from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np

from modeling.io_utils import load_table
from modeling.surrogate import build_surrogate_pipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
SIMULATE_SCRIPT = REPO_ROOT / "scripts" / "training" / "simulate_optimization.py"


def resolve_strategy(strategy: str, args: argparse.Namespace) -> tuple[str, list[str]]:
    if strategy == "greedy":
        return "adaptive", ["--beta", "0.0"]
    if strategy == "adaptive":
        return "adaptive", ["--beta", str(args.beta)]
    if strategy == "contextual_linucb":
        return (
            "contextual_linucb",
            [
                "--reward-mode",
                args.reward_mode,
                "--linucb-alpha",
                str(args.linucb_alpha),
                "--linucb-lambda",
                str(args.linucb_lambda),
            ],
        )
    if strategy == "bandit_ucb":
        return "bandit_ucb", ["--reward-mode", args.reward_mode]
    return strategy, []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Group-holdout generalization benchmark for optimization strategies."
    )
    parser.add_argument("--data", required=True, help="Dataset path (.csv or .xlsx).")
    parser.add_argument("--target", required=True, help="Target column.")
    parser.add_argument(
        "--group-col",
        required=True,
        help="Column used for group holdout (e.g., substrate identifier).",
    )
    parser.add_argument(
        "--features",
        default="",
        help="Comma-separated feature columns. If omitted, all columns except target/group are used.",
    )
    parser.add_argument("--folds", type=int, default=3, help="Number of group folds.")
    parser.add_argument("--seeds", type=int, default=5, help="Seeds per fold.")
    parser.add_argument("--budget", type=int, default=20, help="Simulation budget.")
    parser.add_argument("--n-init", type=int, default=3, help="Initial random observations.")
    parser.add_argument(
        "--strategies",
        default="random,adaptive,contextual_linucb",
        help="Comma-separated strategies to compare.",
    )
    parser.add_argument("--beta", type=float, default=0.8, help="Adaptive UCB beta.")
    parser.add_argument(
        "--reward-mode",
        choices=["yield", "improvement"],
        default="improvement",
        help="Reward mode for bandit strategies.",
    )
    parser.add_argument(
        "--linucb-alpha", type=float, default=1.0, help="LinUCB exploration coefficient."
    )
    parser.add_argument(
        "--linucb-lambda", type=float, default=1.0, help="LinUCB regularization."
    )
    parser.add_argument("--seed", type=int, default=42, help="Global split seed.")
    parser.add_argument(
        "--out-json",
        default="artifacts/benchmark_generalization.json",
        help="Output JSON summary.",
    )
    return parser.parse_args()


def run_simulation(
    strategy: str,
    seed: int,
    data_path: Path,
    model_path: Path,
    args: argparse.Namespace,
    out_path: Path,
) -> Dict:
    cmd = [
        sys.executable,
        str(SIMULATE_SCRIPT),
        "--data",
        str(data_path),
        "--model",
        str(model_path),
        "--strategy",
        "random",
        "--budget",
        str(args.budget),
        "--n-init",
        str(args.n_init),
        "--seed",
        str(seed),
        "--out",
        str(out_path),
    ]
    sim_strategy, extra = resolve_strategy(strategy, args)
    cmd[cmd.index("--strategy") + 1] = sim_strategy
    cmd += extra

    subprocess.run(cmd, check=True)
    with out_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def trajectory_auc(history: List[Dict]) -> float:
    return float(sum(float(step["best_so_far"]) for step in history)) if history else 0.0


def step_to_threshold(history: List[Dict], threshold: float) -> Optional[int]:
    for step in history:
        if float(step["best_so_far"]) >= threshold:
            return int(step["step"])
    return None


def main() -> None:
    args = parse_args()
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    if "random" not in strategies:
        raise ValueError("Include random in --strategies for baseline comparison.")

    df = load_table(args.data).copy()
    if args.group_col not in df.columns:
        raise ValueError(f"Group column '{args.group_col}' not found.")
    if args.target not in df.columns:
        raise ValueError(f"Target column '{args.target}' not found.")

    if args.features.strip():
        feature_columns = [c.strip() for c in args.features.split(",") if c.strip()]
    else:
        feature_columns = [c for c in df.columns if c not in {args.target, args.group_col}]

    missing_features = [c for c in feature_columns if c not in df.columns]
    if missing_features:
        raise ValueError(f"Missing feature columns: {missing_features}")

    groups = df[args.group_col].dropna().astype(str).unique().tolist()
    if len(groups) < args.folds:
        raise ValueError("Number of unique groups is smaller than requested folds.")

    rng = np.random.default_rng(args.seed)
    rng.shuffle(groups)
    fold_groups = np.array_split(np.array(groups), args.folds)

    base_dir = Path("artifacts/_generalization_runs")
    base_dir.mkdir(parents=True, exist_ok=True)

    per_strategy: Dict[str, List[Dict]] = {s: [] for s in strategies}

    for fold_idx, test_groups_arr in enumerate(fold_groups):
        test_groups = set(test_groups_arr.tolist())
        train_df = df[~df[args.group_col].astype(str).isin(test_groups)].copy()
        test_df = df[df[args.group_col].astype(str).isin(test_groups)].copy()

        if len(test_df) < max(args.budget, args.n_init + 1):
            continue

        fold_dir = base_dir / f"fold_{fold_idx}"
        fold_dir.mkdir(parents=True, exist_ok=True)
        holdout_data_path = fold_dir / "holdout.csv"
        model_path = fold_dir / "surrogate_fold.joblib"

        # Train on train groups only.
        pipeline = build_surrogate_pipeline(train_df, feature_columns)
        pipeline.fit(train_df[feature_columns], train_df[args.target])

        bundle = {
            "pipeline": pipeline,
            "feature_columns": feature_columns,
            "target_column": args.target,
        }
        joblib.dump(bundle, model_path)
        test_df.to_csv(holdout_data_path, index=False)

        for seed in range(args.seeds):
            seed_payloads: Dict[str, Dict] = {}
            for strategy in strategies:
                out_path = fold_dir / f"{strategy}_seed_{seed}.json"
                payload = run_simulation(
                    strategy=strategy,
                    seed=seed,
                    data_path=holdout_data_path,
                    model_path=model_path,
                    args=args,
                    out_path=out_path,
                )
                seed_payloads[strategy] = payload

            random_payload = seed_payloads["random"]
            random_best = float(random_payload["best_yield"])
            random_auc = trajectory_auc(random_payload["history"])
            threshold = 0.95 * max(float(p["best_yield"]) for p in seed_payloads.values())
            random_ttr = step_to_threshold(random_payload["history"], threshold)

            for strategy, payload in seed_payloads.items():
                best = float(payload["best_yield"])
                auc = trajectory_auc(payload["history"])
                ttr = step_to_threshold(payload["history"], threshold)
                per_strategy[strategy].append(
                    {
                        "fold": fold_idx,
                        "seed": seed,
                        "best_yield": best,
                        "trajectory_auc": auc,
                        "threshold": threshold,
                        "time_to_threshold": ttr,
                        "best_uplift_vs_random": best - random_best,
                        "auc_uplift_vs_random": auc - random_auc,
                        "wins_vs_random": best > random_best,
                        "faster_than_random": (
                            random_ttr is None or (ttr is not None and ttr < random_ttr)
                        ),
                    }
                )

    summary = {
        "config": {
            "data": args.data,
            "target": args.target,
            "group_col": args.group_col,
            "features": feature_columns,
            "folds": args.folds,
            "seeds_per_fold": args.seeds,
            "budget": args.budget,
            "n_init": args.n_init,
            "strategies": strategies,
        },
        "aggregates": {},
    }

    for strategy, rows in per_strategy.items():
        if not rows:
            summary["aggregates"][strategy] = {"error": "No rows evaluated."}
            continue
        best_vals = [r["best_yield"] for r in rows]
        auc_vals = [r["trajectory_auc"] for r in rows]
        best_uplifts = [r["best_uplift_vs_random"] for r in rows]
        auc_uplifts = [r["auc_uplift_vs_random"] for r in rows]
        wins = [1.0 if r["wins_vs_random"] else 0.0 for r in rows]
        faster = [1.0 if r["faster_than_random"] else 0.0 for r in rows]

        summary["aggregates"][strategy] = {
            "n_runs": int(len(rows)),
            "best_yield_mean": float(np.mean(best_vals)),
            "best_yield_std": float(np.std(best_vals)),
            "trajectory_auc_mean": float(np.mean(auc_vals)),
            "trajectory_auc_std": float(np.std(auc_vals)),
            "threshold_hit_rate": float(
                np.mean([1.0 if r["time_to_threshold"] is not None else 0.0 for r in rows])
            ),
            "avg_step_to_threshold_when_hit": (
                float(
                    np.mean(
                        [r["time_to_threshold"] for r in rows if r["time_to_threshold"] is not None]
                    )
                )
                if any(r["time_to_threshold"] is not None for r in rows)
                else None
            ),
            "best_uplift_vs_random_mean": float(np.mean(best_uplifts)),
            "auc_uplift_vs_random_mean": float(np.mean(auc_uplifts)),
            "win_rate_vs_random": float(np.mean(wins)),
            "faster_than_random_rate": float(np.mean(faster)),
        }

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary["aggregates"], indent=2))
    print(f"Saved generalization benchmark summary: {out_path}")


if __name__ == "__main__":
    main()
