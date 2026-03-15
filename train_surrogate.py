from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib

from modeling.io_utils import load_table
from modeling.surrogate import train_and_evaluate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train LabPilot surrogate model.")
    parser.add_argument("--data", required=True, help="Path to dataset (.csv or .xlsx).")
    parser.add_argument("--target", required=True, help="Target column (e.g., yield).")
    parser.add_argument(
        "--features",
        default="",
        help="Comma-separated feature columns. If omitted, all columns except target are used.",
    )
    parser.add_argument(
        "--out-model",
        default="artifacts/surrogate.joblib",
        help="Output path for trained model pipeline.",
    )
    parser.add_argument(
        "--out-meta",
        default="artifacts/surrogate_meta.json",
        help="Output path for metadata/metrics JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = load_table(args.data)

    if args.target not in df.columns:
        raise ValueError(f"Target column '{args.target}' not found in dataset.")

    if args.features.strip():
        feature_columns = [col.strip() for col in args.features.split(",") if col.strip()]
    else:
        feature_columns = [col for col in df.columns if col != args.target]

    missing = [col for col in feature_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing feature columns: {missing}")

    model, metrics = train_and_evaluate(df, feature_columns, args.target)

    out_model = Path(args.out_model)
    out_meta = Path(args.out_meta)
    out_model.parent.mkdir(parents=True, exist_ok=True)
    out_meta.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(
        {
            "pipeline": model,
            "feature_columns": feature_columns,
            "target_column": args.target,
        },
        out_model,
    )

    with out_meta.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "data_path": str(args.data),
                "target_column": args.target,
                "feature_columns": feature_columns,
                "metrics": metrics,
            },
            f,
            indent=2,
        )

    print("Surrogate model trained.")
    print(json.dumps(metrics, indent=2))
    print(f"Saved model: {out_model}")
    print(f"Saved metadata: {out_meta}")


if __name__ == "__main__":
    main()

