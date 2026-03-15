from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


@dataclass
class SurrogateArtifacts:
    feature_columns: List[str]
    target_column: str
    pipeline: Pipeline


def build_surrogate_pipeline(df: pd.DataFrame, feature_columns: List[str]) -> Pipeline:
    numeric_features = [
        col for col in feature_columns if pd.api.types.is_numeric_dtype(df[col])
    ]
    categorical_features = [col for col in feature_columns if col not in numeric_features]

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                    ]
                ),
                numeric_features,
            ),
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical_features,
            ),
        ],
        remainder="drop",
    )

    model = RandomForestRegressor(
        n_estimators=300,
        random_state=42,
        n_jobs=-1,
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", model),
        ]
    )


def train_and_evaluate(
    df: pd.DataFrame,
    feature_columns: List[str],
    target_column: str,
    test_size: float = 0.2,
    random_state: int = 42,
) -> Tuple[Pipeline, dict]:
    X = df[feature_columns]
    y = df[target_column]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )

    pipeline = build_surrogate_pipeline(df, feature_columns)
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    metrics = {
        "mae": float(mean_absolute_error(y_test, y_pred)),
        "r2": float(r2_score(y_test, y_pred)),
        "train_size": int(len(X_train)),
        "test_size": int(len(X_test)),
    }
    return pipeline, metrics


def predict_with_uncertainty(pipeline: Pipeline, X: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    preprocessor = pipeline.named_steps["preprocessor"]
    model: RandomForestRegressor = pipeline.named_steps["model"]

    Xt = preprocessor.transform(X)
    tree_predictions = pd.DataFrame([tree.predict(Xt) for tree in model.estimators_])

    mean_pred = tree_predictions.mean(axis=0)
    std_pred = tree_predictions.std(axis=0).fillna(0.0)
    return mean_pred, std_pred

