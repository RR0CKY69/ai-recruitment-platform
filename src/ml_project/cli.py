"""Command-line interface for training a tabular classification model."""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import pandas as pd

from ml_project.modeling import train_classifier


def main() -> None:
    parser = argparse.ArgumentParser(prog="ml-project")
    subparsers = parser.add_subparsers(dest="command", required=True)
    train_parser = subparsers.add_parser("train", help="train and evaluate a classifier")
    train_parser.add_argument("--data", type=Path, required=True, help="input CSV file")
    train_parser.add_argument("--target", required=True, help="name of the label column")
    train_parser.add_argument("--output", type=Path, required=True, help="model output path")
    args = parser.parse_args()

    if not args.data.is_file():
        parser.error(f"data file does not exist: {args.data}")

    data = pd.read_csv(args.data)
    if args.target not in data.columns:
        parser.error(f"target column {args.target!r} is not present in the CSV")

    features = data.drop(columns=[args.target])
    target = data[args.target]
    result = train_classifier(features, target)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(result.model, args.output)
    print(f"Holdout accuracy: {result.accuracy:.3f}")
    print(f"Saved model to: {args.output}")
    print(pd.DataFrame(result.report).transpose().round(3).to_string())


if __name__ == "__main__":
    main()