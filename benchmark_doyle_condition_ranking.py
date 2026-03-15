from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Condition-ranking benchmark on Doyle data with substrate holdout."
    )
    parser.add_argument(
        "--raw-data",
        default="data/doyle_data/Doyle_raw_data.csv",
        help="Path to Doyle raw data CSV.",
    )
    parser.add_argument(
        "--aryl-dft",
        default="data/doyle_data/aryl_halide_DFT.csv",
        help="Path to aryl halide descriptor CSV.",
    )
    parser.add_argument(
        "--additive-dft",
        default="data/doyle_data/additive_DFT.csv",
        help="Path to additive descriptor CSV.",
    )
    parser.add_argument("--yield-col", default="yield", help="Yield column.")
    parser.add_argument("--test-frac", type=float, default=0.25, help="Holdout substrate fraction.")
    parser.add_argument("--seeds", type=int, default=20, help="Random split seeds.")
    parser.add_argument(
        "--out-json",
        default="artifacts/benchmark_doyle_condition_ranking.json",
        help="Output benchmark summary JSON.",
    )
    return parser.parse_args()


def hit_at_k(ranked_idx: List[int], target_idx: int, k: int) -> float:
    return 1.0 if target_idx in ranked_idx[:k] else 0.0


def reciprocal_rank(ranked_idx: List[int], target_idx: int) -> float:
    for i, idx in enumerate(ranked_idx, start=1):
        if idx == target_idx:
            return 1.0 / i
    return 0.0


def main() -> None:
    args = parse_args()

    raw = pd.read_csv(args.raw_data)
    aryl_dft = pd.read_csv(args.aryl_dft).reset_index(drop=True)
    add_dft = pd.read_csv(args.additive_dft).reset_index(drop=True)

    # Create 1-based IDs matching raw aryl_halide_number / additive_number convention.
    aryl_dft = aryl_dft.copy()
    aryl_dft["aryl_halide_number"] = np.arange(1, len(aryl_dft) + 1)
    add_dft = add_dft.copy()
    add_dft["additive_number"] = np.arange(1, len(add_dft) + 1)

    df = raw.dropna(subset=["aryl_halide_number", "additive_number", args.yield_col]).copy()
    df["aryl_halide_number"] = df["aryl_halide_number"].astype(int)
    df["additive_number"] = df["additive_number"].astype(int)

    # Keep rows where descriptor mappings exist.
    df = df[
        df["aryl_halide_number"].between(1, len(aryl_dft))
        & df["additive_number"].between(1, len(add_dft))
    ].copy()

    df = df.merge(aryl_dft, on="aryl_halide_number", how="left")
    df = df.merge(add_dft, on="additive_number", how="left")
    df = df.dropna(subset=[args.yield_col]).copy()

    if df.empty:
        raise ValueError("No rows left after descriptor merge.")

    # Input features include condition identity + substrate/additive descriptors.
    categorical_cols = ["base", "ligand"]
    numeric_cols = [
        c
        for c in df.columns
        if c not in categorical_cols + [args.yield_col]
        and pd.api.types.is_numeric_dtype(df[c])
    ]

    # Exclude obvious plate layout leakage columns.
    for leak in ["plate", "row", "col"]:
        if leak in numeric_cols:
            numeric_cols.remove(leak)

    feature_cols = categorical_cols + numeric_cols

    model = Pipeline(
        steps=[
            (
                "preprocessor",
                ColumnTransformer(
                    transformers=[
                        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
                        ("num", "passthrough", numeric_cols),
                    ],
                    remainder="drop",
                ),
            ),
            (
                "regressor",
                RandomForestRegressor(
                    n_estimators=500,
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )

    substrate_ids = sorted(df["aryl_halide_number"].dropna().unique().tolist())
    rng = np.random.default_rng(42)

    seed_rows: List[Dict] = []
    for seed in range(args.seeds):
        seed_rng = np.random.default_rng(int(rng.integers(1, 1_000_000)))
        ids = substrate_ids.copy()
        seed_rng.shuffle(ids)

        n_test = max(1, int(len(ids) * args.test_frac))
        test_ids = set(ids[:n_test])
        train_df = df[~df["aryl_halide_number"].isin(test_ids)].copy()
        test_df = df[df["aryl_halide_number"].isin(test_ids)].copy()
        if train_df.empty or test_df.empty:
            continue

        model.fit(train_df[feature_cols], train_df[args.yield_col])
        test_df = test_df.copy()
        test_df["pred_yield"] = model.predict(test_df[feature_cols])

        top1 = []
        top3 = []
        top5 = []
        mrr = []
        r_top1 = []
        r_top3 = []
        r_top5 = []
        r_mrr = []

        for sid, grp in test_df.groupby("aryl_halide_number"):
            if len(grp) < 2:
                continue
            grp = grp.reset_index(drop=True)
            true_best_idx = int(grp[args.yield_col].idxmax())

            pred_rank = grp["pred_yield"].sort_values(ascending=False).index.tolist()
            rand_rank = list(seed_rng.permutation(grp.index.tolist()))

            top1.append(hit_at_k(pred_rank, true_best_idx, 1))
            top3.append(hit_at_k(pred_rank, true_best_idx, 3))
            top5.append(hit_at_k(pred_rank, true_best_idx, 5))
            mrr.append(reciprocal_rank(pred_rank, true_best_idx))

            r_top1.append(hit_at_k(rand_rank, true_best_idx, 1))
            r_top3.append(hit_at_k(rand_rank, true_best_idx, 3))
            r_top5.append(hit_at_k(rand_rank, true_best_idx, 5))
            r_mrr.append(reciprocal_rank(rand_rank, true_best_idx))

        if not top1:
            continue

        seed_rows.append(
            {
                "seed": seed,
                "n_train_rows": int(len(train_df)),
                "n_test_rows": int(len(test_df)),
                "n_test_substrates": int(test_df["aryl_halide_number"].nunique()),
                "top1": float(np.mean(top1)),
                "top3": float(np.mean(top3)),
                "top5": float(np.mean(top5)),
                "mrr": float(np.mean(mrr)),
                "random_top1": float(np.mean(r_top1)),
                "random_top3": float(np.mean(r_top3)),
                "random_top5": float(np.mean(r_top5)),
                "random_mrr": float(np.mean(r_mrr)),
            }
        )

    if not seed_rows:
        raise ValueError("No benchmark seed rows produced.")

    def agg_mean(key: str) -> float:
        return float(np.mean([r[key] for r in seed_rows]))

    def agg_std(key: str) -> float:
        return float(np.std([r[key] for r in seed_rows]))

    summary = {
        "config": {
            "raw_data": args.raw_data,
            "aryl_dft": args.aryl_dft,
            "additive_dft": args.additive_dft,
            "yield_col": args.yield_col,
            "test_frac": args.test_frac,
            "seeds": args.seeds,
        },
        "dataset_stats": {
            "rows_used": int(len(df)),
            "substrates_used": int(df["aryl_halide_number"].nunique()),
            "feature_count": int(len(feature_cols)),
        },
        "aggregates": {
            "descriptor_condition_ranking": {
                "top1_mean": agg_mean("top1"),
                "top1_std": agg_std("top1"),
                "top3_mean": agg_mean("top3"),
                "top3_std": agg_std("top3"),
                "top5_mean": agg_mean("top5"),
                "top5_std": agg_std("top5"),
                "mrr_mean": agg_mean("mrr"),
                "mrr_std": agg_std("mrr"),
            },
            "random_baseline": {
                "top1_mean": agg_mean("random_top1"),
                "top1_std": agg_std("random_top1"),
                "top3_mean": agg_mean("random_top3"),
                "top3_std": agg_std("random_top3"),
                "top5_mean": agg_mean("random_top5"),
                "top5_std": agg_std("random_top5"),
                "mrr_mean": agg_mean("random_mrr"),
                "mrr_std": agg_std("random_mrr"),
            },
        },
        "seed_rows": seed_rows,
    }

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary["aggregates"], indent=2))
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

