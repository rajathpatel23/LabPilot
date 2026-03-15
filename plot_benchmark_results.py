from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot benchmark summary JSON outputs.")
    parser.add_argument(
        "--benchmark-json",
        required=True,
        help="Path to benchmark summary JSON (e.g., benchmark_generalization_*.json).",
    )
    parser.add_argument(
        "--out-dir",
        default="artifacts/plots",
        help="Directory for saved figures.",
    )
    parser.add_argument(
        "--title-prefix",
        default="",
        help="Optional title prefix for plots.",
    )
    return parser.parse_args()


def _safe_value(d: Dict, key: str, default=np.nan) -> float:
    val = d.get(key, default)
    try:
        if val is None:
            return float("nan")
        return float(val)
    except Exception:
        return float("nan")


def plot_best_yield(aggregates: Dict[str, Dict], out_file: Path, title_prefix: str = "") -> None:
    strategies = list(aggregates.keys())
    means = [_safe_value(aggregates[s], "best_yield_mean") for s in strategies]
    stds = [_safe_value(aggregates[s], "best_yield_std", 0.0) for s in strategies]

    plt.figure(figsize=(8, 4.5))
    bars = plt.bar(strategies, means, yerr=stds, capsize=4)
    plt.ylabel("Best yield (mean +/- std)")
    plt.title(f"{title_prefix} Best Yield by Strategy".strip())
    plt.grid(axis="y", alpha=0.25)
    for b, m in zip(bars, means):
        plt.text(b.get_x() + b.get_width() / 2, m, f"{m:.2f}", ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    plt.savefig(out_file, dpi=160)
    plt.close()


def plot_auc(aggregates: Dict[str, Dict], out_file: Path, title_prefix: str = "") -> None:
    strategies = list(aggregates.keys())
    means = [_safe_value(aggregates[s], "trajectory_auc_mean") for s in strategies]
    stds = [_safe_value(aggregates[s], "trajectory_auc_std", 0.0) for s in strategies]

    plt.figure(figsize=(8, 4.5))
    bars = plt.bar(strategies, means, yerr=stds, capsize=4)
    plt.ylabel("Trajectory AUC (mean +/- std)")
    plt.title(f"{title_prefix} Trajectory AUC by Strategy".strip())
    plt.grid(axis="y", alpha=0.25)
    for b, m in zip(bars, means):
        plt.text(b.get_x() + b.get_width() / 2, m, f"{m:.1f}", ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    plt.savefig(out_file, dpi=160)
    plt.close()


def plot_threshold(aggregates: Dict[str, Dict], out_file: Path, title_prefix: str = "") -> None:
    strategies = list(aggregates.keys())
    vals = [_safe_value(aggregates[s], "threshold_hit_rate", np.nan) for s in strategies]

    plt.figure(figsize=(8, 4.5))
    valid = [v for v in vals if not np.isnan(v)]
    if not valid:
        plt.text(
            0.5,
            0.5,
            "threshold_hit_rate not present in benchmark JSON.\nRe-run benchmark with threshold metrics enabled.",
            ha="center",
            va="center",
            fontsize=11,
        )
        plt.xlim(0, 1)
        plt.ylim(0, 1)
        plt.xticks([])
        plt.yticks([])
        plt.title(f"{title_prefix} Threshold Hit Rate".strip())
    else:
        bars = plt.bar(strategies, vals)
        plt.ylim(0, 1.0)
        plt.ylabel("Threshold hit rate")
        plt.title(f"{title_prefix} Threshold Hit Rate".strip())
        plt.grid(axis="y", alpha=0.25)
        for b, v in zip(bars, vals):
            if np.isnan(v):
                continue
            plt.text(
                b.get_x() + b.get_width() / 2,
                v,
                f"{v:.2f}",
                ha="center",
                va="bottom",
                fontsize=9,
            )
    plt.tight_layout()
    plt.savefig(out_file, dpi=160)
    plt.close()


def main() -> None:
    args = parse_args()
    in_path = Path(args.benchmark_json)
    with in_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    aggregates: Dict[str, Dict] = payload.get("aggregates", {})
    if not aggregates:
        raise ValueError("No 'aggregates' found in benchmark JSON.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = in_path.stem

    best_file = out_dir / f"{stem}_best_yield.png"
    auc_file = out_dir / f"{stem}_trajectory_auc.png"
    thr_file = out_dir / f"{stem}_threshold_hit_rate.png"

    plot_best_yield(aggregates, best_file, args.title_prefix)
    plot_auc(aggregates, auc_file, args.title_prefix)
    plot_threshold(aggregates, thr_file, args.title_prefix)

    print(f"Saved plot: {best_file}")
    print(f"Saved plot: {auc_file}")
    print(f"Saved plot: {thr_file}")


if __name__ == "__main__":
    main()

