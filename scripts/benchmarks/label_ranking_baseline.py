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
        description="Minimal label-ranking style baseline for condition recommendation."
    )
    parser.add_argument("--data", required=True, help="Path to Doyle-style dataset CSV/XLSX.")
    parser.add_argument(
        "--substrate-cols",
        default="aryl_halide,aryl_halide_smiles",
        help="Comma-separated substrate/context columns used as model input.",
    )
    parser.add_argument(
        "--condition-cols",
        default="base,ligand,additive",
        help="Comma-separated condition columns to rank.",
    )
    parser.add_argument("--yield-col", default="yield", help="Yield column name.")
    parser.add_argument(
        "--test-frac",
        type=float,
        default=0.25,
        help="Fraction of substrates held out for evaluation.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--out-json",
        default="artifacts/label_ranking_baseline.json",
        help="Path for summary metrics/output.",
    )
    return parser.parse_args()


def condition_label(row: pd.Series, condition_cols: List[str]) -> str:
    parts = []
    for col in condition_cols:
        val = row[col]
        parts.append(f"{col}={val if pd.notnull(val) else 'NULL'}")
    return "|".join(parts)


def topk_hit(pred_ranked: List[str], true_best: str, k: int) -> float:
    return 1.0 if true_best in pred_ranked[:k] else 0.0


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed)

    substrate_cols = [c.strip() for c in args.substrate_cols.split(",") if c.strip()]
    condition_cols = [c.strip() for c in args.condition_cols.split(",") if c.strip()]

    df = load_table(args.data).copy()
    needed = substrate_cols + condition_cols + [args.yield_col]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df[needed].copy()
    df["condition_label"] = df.apply(
        lambda row: condition_label(row, condition_cols), axis=1
    )

    # Aggregate repeated measurements.
    grouped = (
        df.groupby(substrate_cols + ["condition_label"], dropna=False)[args.yield_col]
        .mean()
        .reset_index()
        .rename(columns={args.yield_col: "mean_yield"})
    )

    # Build per-substrate rankings of condition labels.
    rankings = (
        grouped.sort_values(substrate_cols + ["mean_yield"], ascending=[True] * len(substrate_cols) + [False])
        .groupby(substrate_cols, dropna=False)
        .agg(
            ranked_conditions=("condition_label", list),
            ranked_yields=("mean_yield", list),
        )
        .reset_index()
    )
    rankings["best_condition"] = rankings["ranked_conditions"].apply(lambda x: x[0])

    # Train/test split by substrate identity.
    rankings = rankings.sample(frac=1.0, random_state=args.seed).reset_index(drop=True)
    n_test = max(1, int(len(rankings) * args.test_frac))
    test_df = rankings.iloc[:n_test].copy()
    train_df = rankings.iloc[n_test:].copy()
    if train_df.empty:
        raise ValueError("Train split is empty. Reduce --test-frac.")

    X_train = train_df[substrate_cols]
    y_train = train_df["best_condition"]
    X_test = test_df[substrate_cols]
    y_test = test_df["best_condition"]

    # Substrate-only classifier predicts best condition probabilities.
    clf = Pipeline(
        steps=[
            (
                "preprocessor",
                ColumnTransformer(
                    transformers=[
                        (
                            "cat",
                            OneHotEncoder(handle_unknown="ignore"),
                            substrate_cols,
                        )
                    ],
                    remainder="drop",
                ),
            ),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=400,
                    random_state=args.seed,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    clf.fit(X_train, y_train)

    proba = clf.predict_proba(X_test)
    classes = clf.named_steps["model"].classes_

    # Random baseline: random ranking over classes.
    random_rankings = []
    for _ in range(len(X_test)):
        random_rankings.append(list(rng.permutation(classes)))

    top1, top3, top5 = [], [], []
    r_top1, r_top3, r_top5 = [], [], []
    sample_rows: List[Dict] = []

    for i in range(len(X_test)):
        order = np.argsort(proba[i])[::-1]
        pred_ranked = [str(classes[j]) for j in order]
        true_best = str(y_test.iloc[i])

        top1.append(topk_hit(pred_ranked, true_best, 1))
        top3.append(topk_hit(pred_ranked, true_best, 3))
        top5.append(topk_hit(pred_ranked, true_best, 5))

        rand_ranked = random_rankings[i]
        r_top1.append(topk_hit(rand_ranked, true_best, 1))
        r_top3.append(topk_hit(rand_ranked, true_best, 3))
        r_top5.append(topk_hit(rand_ranked, true_best, 5))

        if i < 5:
            sample_rows.append(
                {
                    "substrate": {
                        col: (None if pd.isna(X_test.iloc[i][col]) else str(X_test.iloc[i][col]))
                        for col in substrate_cols
                    },
                    "true_best_condition": true_best,
                    "pred_top3": pred_ranked[:3],
                }
            )

    summary = {
        "data_path": args.data,
        "substrate_cols": substrate_cols,
        "condition_cols": condition_cols,
        "yield_col": args.yield_col,
        "n_substrates_total": int(len(rankings)),
        "n_train_substrates": int(len(train_df)),
        "n_test_substrates": int(len(test_df)),
        "metrics": {
            "label_ranking_style": {
                "top1_accuracy": float(np.mean(top1)),
                "top3_hit_rate": float(np.mean(top3)),
                "top5_hit_rate": float(np.mean(top5)),
            },
            "random_baseline": {
                "top1_accuracy": float(np.mean(r_top1)),
                "top3_hit_rate": float(np.mean(r_top3)),
                "top5_hit_rate": float(np.mean(r_top5)),
            },
        },
        "sample_predictions": sample_rows,
        "notes": (
            "This is a minimal substrate-only condition-ranking baseline. "
            "It predicts best-condition probabilities and ranks condition labels accordingly."
        ),
    }

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary["metrics"], indent=2))
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

