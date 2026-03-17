from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare random vs adaptive optimization trajectories."
    )
    parser.add_argument("--random", required=True, help="Path to random simulation JSON.")
    parser.add_argument(
        "--adaptive", required=True, help="Path to adaptive simulation JSON."
    )
    parser.add_argument(
        "--out-csv",
        default="artifacts/trajectory_comparison.csv",
        help="Output CSV with side-by-side trajectories.",
    )
    parser.add_argument(
        "--target-yield",
        type=float,
        default=None,
        help="Optional fixed target yield for time-to-threshold comparison.",
    )
    return parser.parse_args()


def load_history(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("history", [])


def best_curve(history: List[Dict], label: str) -> pd.DataFrame:
    rows = []
    for item in history:
        rows.append(
            {
                "step": int(item["step"]),
                "strategy": label,
                "best_so_far": float(item["best_so_far"]),
                "observed_yield": float(item["observed_yield"]),
            }
        )
    return pd.DataFrame(rows).sort_values("step")


def first_step_reaching(df: pd.DataFrame, threshold: float) -> int | None:
    hit = df[df["best_so_far"] >= threshold]
    if hit.empty:
        return None
    return int(hit["step"].min())


def main() -> None:
    args = parse_args()
    random_df = best_curve(load_history(args.random), "random")
    adaptive_df = best_curve(load_history(args.adaptive), "adaptive")

    merged = pd.merge(
        random_df[["step", "best_so_far"]].rename(columns={"best_so_far": "random_best"}),
        adaptive_df[["step", "best_so_far"]].rename(
            columns={"best_so_far": "adaptive_best"}
        ),
        on="step",
        how="outer",
    ).sort_values("step")
    merged["uplift_abs"] = merged["adaptive_best"] - merged["random_best"]
    merged["uplift_pct"] = (merged["uplift_abs"] / merged["random_best"].replace(0, pd.NA)) * 100

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_csv, index=False)

    random_final = float(random_df["best_so_far"].iloc[-1])
    adaptive_final = float(adaptive_df["best_so_far"].iloc[-1])
    final_uplift_abs = adaptive_final - random_final
    final_uplift_pct = (final_uplift_abs / random_final * 100.0) if random_final != 0 else None

    # Area under best-so-far curve as a compact "trajectory quality" metric.
    random_auc = float(random_df["best_so_far"].sum())
    adaptive_auc = float(adaptive_df["best_so_far"].sum())

    if args.target_yield is not None:
        threshold = float(args.target_yield)
    else:
        # If not provided, use 95% of the best value reached by either strategy.
        threshold = 0.95 * max(random_final, adaptive_final)

    random_ttr = first_step_reaching(random_df, threshold)
    adaptive_ttr = first_step_reaching(adaptive_df, threshold)

    summary = {
        "final_best": {
            "random": random_final,
            "adaptive": adaptive_final,
            "uplift_abs": final_uplift_abs,
            "uplift_pct": final_uplift_pct,
        },
        "trajectory_auc": {
            "random": random_auc,
            "adaptive": adaptive_auc,
            "uplift_abs": adaptive_auc - random_auc,
        },
        "time_to_threshold": {
            "threshold": threshold,
            "random_step": random_ttr,
            "adaptive_step": adaptive_ttr,
        },
        "comparison_csv": str(out_csv),
    }

    print(json.dumps(summary, indent=2))
    print(f"Saved trajectory comparison CSV: {out_csv}")


if __name__ == "__main__":
    main()

