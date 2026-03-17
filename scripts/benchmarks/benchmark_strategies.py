from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
SIMULATE_SCRIPT = REPO_ROOT / "scripts" / "training" / "simulate_optimization.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run multi-seed benchmark across optimization strategies."
    )
    parser.add_argument("--data", required=True, help="Dataset path (.csv or .xlsx).")
    parser.add_argument("--model", required=True, help="Trained surrogate joblib path.")
    parser.add_argument("--budget", type=int, default=20, help="Experiment budget.")
    parser.add_argument("--n-init", type=int, default=3, help="Initial random observations.")
    parser.add_argument("--seeds", type=int, default=20, help="Number of random seeds.")
    parser.add_argument(
        "--strategies",
        default="random,greedy,adaptive,contextual_linucb",
        help="Comma-separated strategy names.",
    )
    parser.add_argument(
        "--reference-strategies",
        default="random,greedy",
        help="Comma-separated reference strategies used for uplift comparisons.",
    )
    parser.add_argument(
        "--reward-mode",
        default="improvement",
        choices=["yield", "improvement"],
        help="Reward mode used by bandit strategies.",
    )
    parser.add_argument("--beta", type=float, default=0.8, help="Adaptive UCB beta.")
    parser.add_argument(
        "--linucb-alpha", type=float, default=1.0, help="Contextual LinUCB alpha."
    )
    parser.add_argument(
        "--linucb-lambda", type=float, default=1.0, help="Contextual LinUCB lambda."
    )
    parser.add_argument(
        "--out-json",
        default="artifacts/benchmark_multi_seed.json",
        help="Output JSON summary path.",
    )
    parser.add_argument(
        "--allow-non-holdout",
        action="store_true",
        help=(
            "Allow in-distribution benchmarking. Disabled by default because it can be leaky. "
            "Use scripts/benchmarks/benchmark_generalization.py for claim-quality evaluation."
        ),
    )
    return parser.parse_args()


def resolve_strategy(strategy: str, args: argparse.Namespace) -> Tuple[str, List[str]]:
    if strategy == "greedy":
        # Greedy = pure exploitation baseline (beta = 0 on adaptive scorer).
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


def run_simulation(
    strategy: str,
    seed: int,
    args: argparse.Namespace,
    out_path: Path,
) -> Dict:
    cmd = [
        sys.executable,
        str(SIMULATE_SCRIPT),
        "--data",
        args.data,
        "--model",
        args.model,
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
    if not history:
        return 0.0
    return float(sum(float(step["best_so_far"]) for step in history))


def step_to_threshold(history: List[Dict], threshold: float) -> Optional[int]:
    for step in history:
        if float(step["best_so_far"]) >= threshold:
            return int(step["step"])
    return None


def bootstrap_ci(values: List[float], n_bootstrap: int = 2000) -> Dict[str, float]:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return {"mean": float("nan"), "ci_lower": float("nan"), "ci_upper": float("nan")}
    rng = np.random.default_rng(12345)
    idx = rng.integers(0, arr.size, size=(n_bootstrap, arr.size))
    means = arr[idx].mean(axis=1)
    return {
        "mean": float(arr.mean()),
        "ci_lower": float(np.percentile(means, 2.5)),
        "ci_upper": float(np.percentile(means, 97.5)),
    }


def main() -> None:
    args = parse_args()
    if not args.allow_non_holdout:
        raise ValueError(
            "Non-holdout benchmark is disabled by default to avoid leaky claims. "
            "Use scripts/benchmarks/benchmark_generalization.py, or pass --allow-non-holdout for diagnostics only."
        )
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    reference_strategies = [
        s.strip() for s in args.reference_strategies.split(",") if s.strip()
    ]
    if "random" not in strategies:
        raise ValueError("Include random strategy for baseline comparison.")
    for ref in reference_strategies:
        if ref not in strategies:
            raise ValueError(f"Reference strategy '{ref}' must be included in --strategies.")

    tmp_dir = Path("artifacts/_benchmark_runs")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    per_strategy: Dict[str, List[Dict]] = {s: [] for s in strategies}

    for seed in range(args.seeds):
        seed_payloads: Dict[str, Dict] = {}
        for strategy in strategies:
            out_path = tmp_dir / f"{strategy}_seed_{seed}.json"
            payload = run_simulation(strategy, seed, args, out_path)
            seed_payloads[strategy] = payload

        threshold = 0.95 * max(float(p["best_yield"]) for p in seed_payloads.values())

        reference_metrics = {}
        for ref in reference_strategies:
            ref_payload = seed_payloads[ref]
            reference_metrics[ref] = {
                "best": float(ref_payload["best_yield"]),
                "auc": trajectory_auc(ref_payload["history"]),
                "ttr": step_to_threshold(ref_payload["history"], threshold),
            }

        for strategy, payload in seed_payloads.items():
            best = float(payload["best_yield"])
            auc = trajectory_auc(payload["history"])
            ttr = step_to_threshold(payload["history"], threshold)
            row = {
                "seed": seed,
                "best_yield": best,
                "trajectory_auc": auc,
                "threshold": threshold,
                "time_to_threshold": ttr,
                "threshold_hit": ttr is not None,
            }
            for ref in reference_strategies:
                ref_best = reference_metrics[ref]["best"]
                ref_auc = reference_metrics[ref]["auc"]
                ref_ttr = reference_metrics[ref]["ttr"]
                row[f"best_uplift_vs_{ref}"] = best - ref_best
                row[f"auc_uplift_vs_{ref}"] = auc - ref_auc
                row[f"wins_vs_{ref}"] = best > ref_best
                row[f"faster_than_{ref}"] = (
                    ref_ttr is None or (ttr is not None and ttr < ref_ttr)
                )
            per_strategy[strategy].append(
                row
            )

    summary = {
        "config": {
            "data": args.data,
            "model": args.model,
            "budget": args.budget,
            "n_init": args.n_init,
            "seeds": args.seeds,
            "strategies": strategies,
            "reference_strategies": reference_strategies,
        },
        "aggregates": {},
    }

    for strategy, rows in per_strategy.items():
        best_vals = [r["best_yield"] for r in rows]
        auc_vals = [r["trajectory_auc"] for r in rows]
        threshold_hits = [1.0 if r["threshold_hit"] else 0.0 for r in rows]
        ttr_vals = [r["time_to_threshold"] for r in rows if r["time_to_threshold"] is not None]
        agg = {
            "n_runs": int(len(rows)),
            "best_yield_mean": float(np.mean(best_vals)),
            "best_yield_std": float(np.std(best_vals)),
            "trajectory_auc_mean": float(np.mean(auc_vals)),
            "trajectory_auc_std": float(np.std(auc_vals)),
            "threshold_hit_rate": float(np.mean(threshold_hits)),
            "avg_step_to_threshold_when_hit": (
                float(np.mean(ttr_vals)) if ttr_vals else None
            ),
            "ci_best_yield_mean_95": bootstrap_ci(best_vals),
            "ci_trajectory_auc_mean_95": bootstrap_ci(auc_vals),
        }
        for ref in reference_strategies:
            best_uplifts = [r[f"best_uplift_vs_{ref}"] for r in rows]
            auc_uplifts = [r[f"auc_uplift_vs_{ref}"] for r in rows]
            wins = [1.0 if r[f"wins_vs_{ref}"] else 0.0 for r in rows]
            faster = [1.0 if r[f"faster_than_{ref}"] else 0.0 for r in rows]
            agg[f"best_uplift_vs_{ref}_mean"] = float(np.mean(best_uplifts))
            agg[f"auc_uplift_vs_{ref}_mean"] = float(np.mean(auc_uplifts))
            agg[f"win_rate_vs_{ref}"] = float(np.mean(wins))
            agg[f"faster_than_{ref}_rate"] = float(np.mean(faster))
            agg[f"ci_best_uplift_vs_{ref}_mean_95"] = bootstrap_ci(best_uplifts)
            agg[f"ci_auc_uplift_vs_{ref}_mean_95"] = bootstrap_ci(auc_uplifts)
        summary["aggregates"][strategy] = agg

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary["aggregates"], indent=2))
    print(f"Saved benchmark summary: {out_path}")


if __name__ == "__main__":
    main()
