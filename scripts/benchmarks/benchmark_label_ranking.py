from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from modeling.io_utils import load_table


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Multi-seed substrate-holdout benchmark for label-ranking style condition recommendation."
    )
    parser.add_argument("--data", required=True, help="Path to Doyle-style dataset (CSV/XLSX).")
    parser.add_argument(
        "--substrate-cols",
        default="aryl_halide,aryl_halide_smiles",
        help="Comma-separated substrate/context columns used as model input and holdout groups.",
    )
    parser.add_argument(
        "--condition-cols",
        default="base,ligand,additive",
        help="Comma-separated condition columns to rank.",
    )
    parser.add_argument("--yield-col", default="yield", help="Yield column name.")
    parser.add_argument("--test-frac", type=float, default=0.25, help="Holdout substrate fraction.")
    parser.add_argument("--seeds", type=int, default=20, help="Number of random splits.")
    parser.add_argument(
        "--out-json",
        default="artifacts/benchmark_label_ranking.json",
        help="Output JSON summary.",
    )
    return parser.parse_args()


def make_condition_label(row: pd.Series, condition_cols: List[str]) -> str:
    vals = []
    for c in condition_cols:
        v = row[c]
        vals.append(f"{c}={v if pd.notnull(v) else 'NULL'}")
    return "|".join(vals)


def hit_at_k(ranked: List[str], target: str, k: int) -> float:
    return 1.0 if target in ranked[:k] else 0.0


def mrr(ranked: List[str], target: str) -> float:
    for i, v in enumerate(ranked, start=1):
        if v == target:
            return 1.0 / i
    return 0.0


def main() -> None:
    args = parse_args()
    substrate_cols = [c.strip() for c in args.substrate_cols.split(",") if c.strip()]
    condition_cols = [c.strip() for c in args.condition_cols.split(",") if c.strip()]

    df = load_table(args.data).copy()
    required = substrate_cols + condition_cols + [args.yield_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df[required].copy()
    df["condition_label"] = df.apply(
        lambda r: make_condition_label(r, condition_cols),
        axis=1,
    )

    # Mean yield per (substrate, condition)
    agg = (
        df.groupby(substrate_cols + ["condition_label"], dropna=False)[args.yield_col]
        .mean()
        .reset_index()
        .rename(columns={args.yield_col: "mean_yield"})
    )

    # Ranking list per substrate
    rankings = (
        agg.sort_values(substrate_cols + ["mean_yield"], ascending=[True] * len(substrate_cols) + [False])
        .groupby(substrate_cols, dropna=False)
        .agg(
            ranked_conditions=("condition_label", list),
            ranked_yields=("mean_yield", list),
        )
        .reset_index()
    )
    rankings["best_condition"] = rankings["ranked_conditions"].apply(lambda x: x[0])

    # Stable group key for substrate split.
    rankings["substrate_key"] = rankings[substrate_cols].astype(str).agg("|".join, axis=1)
    substrate_keys = rankings["substrate_key"].unique().tolist()

    all_rows = []
    rng = np.random.default_rng(42)
    for seed in range(args.seeds):
        seed_rng = np.random.default_rng(int(rng.integers(1, 1_000_000)))
        keys = substrate_keys.copy()
        seed_rng.shuffle(keys)

        n_test = max(1, int(len(keys) * args.test_frac))
        test_keys = set(keys[:n_test])
        train_df = rankings[~rankings["substrate_key"].isin(test_keys)].copy()
        test_df = rankings[rankings["substrate_key"].isin(test_keys)].copy()
        if train_df.empty or test_df.empty:
            continue

        X_train = train_df[substrate_cols]
        y_train = train_df["best_condition"]
        X_test = test_df[substrate_cols]
        y_test = test_df["best_condition"].astype(str).tolist()

        model = Pipeline(
            steps=[
                (
                    "preprocessor",
                    ColumnTransformer(
                        transformers=[
                            ("cat", OneHotEncoder(handle_unknown="ignore"), substrate_cols),
                        ],
                        remainder="drop",
                    ),
                ),
                (
                    "clf",
                    RandomForestClassifier(
                        n_estimators=400,
                        random_state=seed,
                        n_jobs=-1,
                    ),
                ),
            ]
        )
        model.fit(X_train, y_train)

        proba = model.predict_proba(X_test)
        classes = [str(c) for c in model.named_steps["clf"].classes_]

        top1_vals = []
        top3_vals = []
        top5_vals = []
        mrr_vals = []
        random_top1 = []
        random_top3 = []
        random_top5 = []
        random_mrr = []

        for i, true_best in enumerate(y_test):
            order = np.argsort(proba[i])[::-1]
            ranked = [classes[j] for j in order]

            top1_vals.append(hit_at_k(ranked, true_best, 1))
            top3_vals.append(hit_at_k(ranked, true_best, 3))
            top5_vals.append(hit_at_k(ranked, true_best, 5))
            mrr_vals.append(mrr(ranked, true_best))

            rand_ranked = list(seed_rng.permutation(classes))
            random_top1.append(hit_at_k(rand_ranked, true_best, 1))
            random_top3.append(hit_at_k(rand_ranked, true_best, 3))
            random_top5.append(hit_at_k(rand_ranked, true_best, 5))
            random_mrr.append(mrr(rand_ranked, true_best))

        all_rows.append(
            {
                "seed": seed,
                "n_train_substrates": int(len(train_df)),
                "n_test_substrates": int(len(test_df)),
                "condition_space_size": int(len(classes)),
                "top1": float(np.mean(top1_vals)),
                "top3": float(np.mean(top3_vals)),
                "top5": float(np.mean(top5_vals)),
                "mrr": float(np.mean(mrr_vals)),
                "random_top1": float(np.mean(random_top1)),
                "random_top3": float(np.mean(random_top3)),
                "random_top5": float(np.mean(random_top5)),
                "random_mrr": float(np.mean(random_mrr)),
            }
        )

    if not all_rows:
        raise ValueError("No benchmark rows produced. Check dataset/split settings.")

    def agg_mean(key: str) -> float:
        return float(np.mean([r[key] for r in all_rows]))

    def agg_std(key: str) -> float:
        return float(np.std([r[key] for r in all_rows]))

    summary = {
        "config": {
            "data": args.data,
            "substrate_cols": substrate_cols,
            "condition_cols": condition_cols,
            "yield_col": args.yield_col,
            "test_frac": args.test_frac,
            "seeds": args.seeds,
        },
        "dataset_stats": {
            "n_substrates": int(len(substrate_keys)),
            "n_condition_labels": int(df["condition_label"].nunique()),
            "n_rows": int(len(df)),
        },
        "aggregates": {
            "label_ranking_style": {
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
        "seed_rows": all_rows,
    }

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary["aggregates"], indent=2))
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

