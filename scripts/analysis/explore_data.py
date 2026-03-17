from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quick EDA for reaction dataset.")
    parser.add_argument("--data", required=True, help="Input dataset path (.csv or .xlsx).")
    parser.add_argument(
        "--target",
        default=None,
        help="Optional target column (e.g., yield). If absent, script will try to infer.",
    )
    parser.add_argument(
        "--max-categories",
        type=int,
        default=12,
        help="Max unique categories for per-category target summaries.",
    )
    parser.add_argument(
        "--out-json",
        default="artifacts/eda_summary.json",
        help="Path to write JSON summary.",
    )
    return parser.parse_args()


def load_dataframe(path: str) -> pd.DataFrame:
    lower = path.lower()
    if lower.endswith(".csv"):
        return pd.read_csv(path)
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        return pd.read_excel(path)
    raise ValueError("Unsupported file type. Use CSV or XLSX.")


def infer_target_column(df: pd.DataFrame) -> Optional[str]:
    candidates = [c for c in df.columns if "yield" in c.lower()]
    if candidates:
        return candidates[0]
    return None


def basic_profile(df: pd.DataFrame) -> Dict:
    dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}
    null_counts = df.isnull().sum().sort_values(ascending=False)
    num_rows, num_cols = df.shape
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    categorical_cols = [col for col in df.columns if col not in numeric_cols]
    return {
        "shape": {"rows": int(num_rows), "columns": int(num_cols)},
        "columns": df.columns.tolist(),
        "dtypes": dtypes,
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "missing_top20": null_counts.head(20).to_dict(),
    }


def target_signal_profile(
    df: pd.DataFrame, target_col: str, max_categories: int
) -> Dict[str, object]:
    out: Dict[str, object] = {}
    if target_col not in df.columns:
        return out

    target_series = pd.to_numeric(df[target_col], errors="coerce")
    out["target"] = {
        "column": target_col,
        "count": int(target_series.notnull().sum()),
        "mean": float(target_series.mean()),
        "std": float(target_series.std()),
        "min": float(target_series.min()),
        "max": float(target_series.max()),
    }

    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    numeric_features = [c for c in numeric_cols if c != target_col]
    corr_rows: List[Dict[str, float]] = []
    for col in numeric_features:
        corr = pd.to_numeric(df[col], errors="coerce").corr(target_series)
        if pd.notnull(corr):
            corr_rows.append({"feature": col, "corr_with_target": float(corr)})
    corr_rows.sort(key=lambda x: abs(x["corr_with_target"]), reverse=True)
    out["numeric_correlations_top10"] = corr_rows[:10]

    category_rows: Dict[str, List[Dict[str, object]]] = {}
    categorical_cols = [c for c in df.columns if c not in numeric_cols]
    for col in categorical_cols:
        nunique = int(df[col].nunique(dropna=True))
        if nunique == 0 or nunique > max_categories:
            continue
        grouped = (
            df.assign(_target_num=target_series)
            .groupby(col, dropna=False)["_target_num"]
            .agg(["count", "mean"])
            .reset_index()
            .sort_values("mean", ascending=False)
        )
        rows: List[Dict[str, object]] = []
        for _, row in grouped.iterrows():
            key = row[col]
            if pd.isna(key):
                key = "NULL"
            rows.append(
                {
                    "category": str(key),
                    "count": int(row["count"]),
                    "target_mean": float(row["mean"]),
                }
            )
        category_rows[col] = rows
    out["categorical_target_summary"] = category_rows
    return out


def main() -> None:
    args = parse_args()
    df = load_dataframe(args.data)

    target_col = args.target if args.target else infer_target_column(df)
    summary = {
        "data_path": args.data,
        "profile": basic_profile(df),
        "target_profile": (
            target_signal_profile(df, target_col, args.max_categories)
            if target_col
            else {"message": "No target provided or inferred. Add --target for signal analysis."}
        ),
    }

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary["profile"]["shape"], indent=2))
    print(f"Target used: {target_col if target_col else 'none'}")
    print(f"Saved EDA summary: {out_path}")


if __name__ == "__main__":
    main()

