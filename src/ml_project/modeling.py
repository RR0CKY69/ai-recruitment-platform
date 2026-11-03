"""Pipeline construction and evaluation for tabular classification."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.compose import ColumnTransformer, make_column_selector
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


@dataclass
class TrainingResult:
    """A fitted model and metrics calculated on its holdout split."""

    model: Pipeline
    accuracy: float
    report: dict


def build_pipeline() -> Pipeline:
    """Build preprocessing and classification as one leakage-safe pipeline."""
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    preprocess = ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, make_column_selector(dtype_include="number")),
            ("categorical", categorical_pipeline, make_column_selector(dtype_exclude="number")),
        ]
    )
    return Pipeline(
        steps=[
            ("preprocess", preprocess),
            ("classifier", RandomForestClassifier(n_estimators=200, random_state=42)),
        ]
    )


def train_classifier(
    features: pd.DataFrame,
    target: pd.Series,
    *,
    test_size: float = 0.2,
    random_state: int = 42,
) -> TrainingResult:
    """Train a classifier and report performance on a stratified holdout split."""
    if features.empty or target.empty:
        raise ValueError("Training data must contain at least one row.")
    if len(features) != len(target):
        raise ValueError("Features and target must contain the same number of rows.")
    if target.nunique() < 2:
        raise ValueError("The target must contain at least two classes.")

    x_train, x_test, y_train, y_test = train_test_split(
        features,
        target,
        test_size=test_size,
        random_state=random_state,
        stratify=target,
    )
    model = build_pipeline()
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    return TrainingResult(
        model=model,
        accuracy=float(accuracy_score(y_test, predictions)),
        report=classification_report(y_test, predictions, output_dict=True, zero_division=0),
    )