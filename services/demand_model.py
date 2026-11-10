from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
SALES_DATA_FILE = BASE_DIR / "data" / "sales_history.csv"

FEATURES = [
    "price",
    "competitor_price",
    "inventory",
    "day_of_week",
    "promotion",
    "seasonal_factor",
]

TARGET = "units_sold"


# --------------------------------------------------
# DATA LOADING AND VALIDATION
# --------------------------------------------------

def load_training_data():
    """Load and validate the historical sales dataset."""

    if not SALES_DATA_FILE.exists():
        raise FileNotFoundError(
            f"Sales history not found: {SALES_DATA_FILE}. "
            "Run generate_data.py to create the dataset."
        )

    data = pd.read_csv(SALES_DATA_FILE)

    required_columns = FEATURES + [TARGET]
    missing_columns = [
        column
        for column in required_columns
        if column not in data.columns
    ]

    if missing_columns:
        raise ValueError(
            "Sales history is missing required columns: "
            + ", ".join(missing_columns)
        )

    if data.empty:
        raise ValueError("Sales history contains no records.")

    # Convert required fields to numeric values.
    for column in required_columns:
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        )

    # Reject missing or non-finite values rather than training
    # on corrupted records.
    if data[required_columns].isnull().any().any():
        raise ValueError(
            "Sales history contains missing or non-numeric values."
        )

    values = data[required_columns].to_numpy(dtype=float)

    if not np.isfinite(values).all():
        raise ValueError(
            "Sales history contains infinite or invalid numeric values."
        )

    if (data["price"] <= 0).any():
        raise ValueError("Historical selling prices must be positive.")

    if (data["competitor_price"] < 0).any():
        raise ValueError("Competitor prices cannot be negative.")

    if (data["inventory"] < 0).any():
        raise ValueError("Inventory values cannot be negative.")

    if (data[TARGET] < 0).any():
        raise ValueError("Units sold cannot be negative.")

    if len(data) < 5:
        raise ValueError(
            "At least five valid records are required to train the model."
        )

    return data


# --------------------------------------------------
# MODEL TRAINING AND EVALUATION
# --------------------------------------------------

def train_model():
    """
    Train a Random Forest demand prediction model.

    Returns:
        A fitted RandomForestRegressor.
    """

    data = load_training_data()

    X = data[FEATURES]
    y = data[TARGET]

    # Keep the split deterministic so evaluation is reproducible.
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
    )

    model = RandomForestRegressor(
        n_estimators=150,
        max_depth=12,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=1,
    )

    model.fit(X_train, y_train)

    # Evaluate predictions on held-out records.
    predictions = model.predict(X_test)

    mae = mean_absolute_error(y_test, predictions)
    rmse = np.sqrt(mean_squared_error(y_test, predictions))

    # R² is not informative for a test set with fewer than two records.
    r2 = (
        r2_score(y_test, predictions)
        if len(y_test) >= 2
        else None
    )

    print("\nDemand Prediction Model Evaluation")
    print("-" * 40)
    print(f"Training records: {len(X_train)}")
    print(f"Testing records: {len(X_test)}")
    print(f"MAE:  {mae:.2f} units")
    print(f"RMSE: {rmse:.2f} units")

    if r2 is not None:
        print(f"R²:   {r2:.3f}")
    else:
        print("R²:   unavailable (fewer than two test records)")

    print("Dataset: synthetic historical sales data")

    return model


# --------------------------------------------------
# STANDALONE EXECUTION
# --------------------------------------------------

if __name__ == "__main__":
    train_model()