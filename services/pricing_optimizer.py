import math
from pathlib import Path

import numpy as np
import pandas as pd

from services.demand_model import FEATURES, train_model


BASE_DIR = Path(__file__).resolve().parent.parent
PRODUCTS_FILE = BASE_DIR / "data" / "products.csv"

NUMBER_OF_CANDIDATES = 31


def optimize_price(product, model):
    """
    Find the candidate selling price with the highest
    model-estimated profit.

    The optimizer:
    - Respects minimum and maximum selling prices.
    - Includes the current price as a baseline.
    - Accounts for inventory and product cost.
    - Returns the existing API response fields.
    """

    # Extract and validate product values.
    try:
        min_price = float(product["min_price"])
        max_price = float(product["max_price"])
        current_price = float(product["current_price"])
        cost_price = float(product["cost_price"])
        inventory = float(product["inventory"])
        competitor_price = float(product["competitor_price"])

    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError(
            "Product contains missing or invalid pricing data."
        ) from error

    numeric_values = [
        min_price,
        max_price,
        current_price,
        cost_price,
        inventory,
        competitor_price,
    ]

    if not all(math.isfinite(value) for value in numeric_values):
        raise ValueError("Product pricing data must contain finite numbers.")

    if min_price <= 0 or max_price < min_price:
        raise ValueError("Invalid minimum or maximum price.")

    if cost_price < 0 or inventory < 0:
        raise ValueError("Cost and inventory cannot be negative.")

    if competitor_price < 0:
        raise ValueError("Competitor price cannot be negative.")

    if not min_price <= current_price <= max_price:
        raise ValueError(
            "Current price must fall within the allowed price range."
        )

    # Generate evenly spaced candidates and include the current price.
    # Round to two decimals to support prices with fractional values.
    candidate_prices = np.linspace(
        min_price,
        max_price,
        NUMBER_OF_CANDIDATES,
    )

    candidate_prices = {
        round(float(price), 2)
        for price in candidate_prices
    }

    candidate_prices.add(round(current_price, 2))
    candidate_prices.add(round(min_price, 2))
    candidate_prices.add(round(max_price, 2))

    results = []

    for price in sorted(candidate_prices):

        # Use the same feature names and order as model training.
        input_data = pd.DataFrame(
            [{
                "price": price,
                "competitor_price": competitor_price,
                "inventory": inventory,
                "day_of_week": 2,
                "promotion": 0,
                "seasonal_factor": 1.0,
            }],
            columns=FEATURES,
        )

        predicted_demand = float(model.predict(input_data)[0])

        if not math.isfinite(predicted_demand):
            raise ValueError(
                "The demand model returned an invalid prediction."
            )

        predicted_demand = max(0.0, predicted_demand)

        # Sales cannot exceed available inventory.
        expected_units_sold = min(predicted_demand, inventory)

        expected_revenue = price * expected_units_sold

        expected_profit = (
            price - cost_price
        ) * expected_units_sold

        results.append({
            "price": round(price, 2),
            "predicted_demand": round(predicted_demand, 2),
            "expected_units_sold": round(expected_units_sold, 2),
            "expected_revenue": round(expected_revenue, 2),
            "expected_profit": round(expected_profit, 2),
        })

    if not results:
        raise ValueError("No valid candidate prices were generated.")

    # Maximize estimated profit. If profits tie, prefer the price
    # closest to the current price.
    best_result = max(
        results,
        key=lambda result: (
            result["expected_profit"],
            -abs(result["price"] - current_price),
        ),
    )

    # Locate the current-price baseline for a direct comparison.
    current_price_rounded = round(current_price, 2)

    current_result = next(
        result
        for result in results
        if result["price"] == current_price_rounded
    )

    profit_change = (
        best_result["expected_profit"]
        - current_result["expected_profit"]
    )

    current_profit = current_result["expected_profit"]

    profit_change_percent = (
        (profit_change / abs(current_profit)) * 100
        if current_profit != 0
        else None
    )

    return {
        "product_id": str(product["product_id"]),
        "product_name": str(product["product_name"]),
        "current_price": round(current_price, 2),
        "recommended_price": best_result["price"],
        "predicted_demand": best_result["predicted_demand"],
        "expected_units_sold": best_result["expected_units_sold"],
        "expected_revenue": best_result["expected_revenue"],
        "expected_profit": best_result["expected_profit"],
        "current_expected_profit": current_result["expected_profit"],
        "estimated_profit_change": round(profit_change, 2),
        "estimated_profit_change_percent": (
            round(profit_change_percent, 2)
            if profit_change_percent is not None
            else None
        ),
        "candidate_results": results,
    }


def optimize_all_products():
    """Generate recommendations for every product in the catalogue."""

    products = pd.read_csv(PRODUCTS_FILE)
    model = train_model()

    return [
        optimize_price(product, model)
        for _, product in products.iterrows()
    ]


if __name__ == "__main__":
    recommendations = optimize_all_products()

    print("\nDYNAMIC PRICING RECOMMENDATIONS")
    print("=" * 65)

    for item in recommendations:
        print(f"\nProduct: {item['product_name']}")
        print(f"Current price: ₹{item['current_price']:.2f}")
        print(f"Recommended price: ₹{item['recommended_price']:.2f}")
        print(f"Current estimated profit: ₹{item['current_expected_profit']:.2f}")
        print(f"Recommended estimated profit: ₹{item['expected_profit']:.2f}")
        print(f"Estimated profit change: ₹{item['estimated_profit_change']:.2f}")

        change_percent = item["estimated_profit_change_percent"]

        if change_percent is not None:
            print(f"Estimated profit change: {change_percent:.2f}%")
        else:
            print("Estimated profit change: percentage unavailable")