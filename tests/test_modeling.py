import pandas as pd
import pytest

from ml_project.modeling import train_classifier


def test_training_handles_numeric_categorical_and_missing_values():
    features = pd.DataFrame(
        {
            "measurement": [1.0, 1.2, 1.1, 8.0, 8.2, 8.1, None, 7.9, 1.3, 8.3],
            "group": ["a", "a", "a", "b", "b", "b", "a", "b", "a", "b"],
        }
    )
    target = pd.Series(["low"] * 5 + ["high"] * 5)

    result = train_classifier(features, target, test_size=0.4)

    assert 0.0 <= result.accuracy <= 1.0
    assert "accuracy" in result.report
    assert set(result.model.predict(features)) == {"low", "high"}


def test_training_rejects_single_class_target():
    features = pd.DataFrame({"measurement": [1, 2, 3, 4]})
    target = pd.Series(["only"] * 4)

    with pytest.raises(ValueError, match="at least two classes"):
        train_classifier(features, target)