import pandas as pd

from services.demand_model import FEATURES, train_model
from services.pricing_optimizer import optimize_price


def evaluate_pricing():
    products = pd.read_csv("data/products.csv")
    model = train_model()

    total_fixed_profit = 0
    total_dynamic_profit = 0

    print("\nFIXED VS DYNAMIC PRICING")
    print("=" * 75)

    for _, product in products.iterrows():
        # Evaluate current fixed price
        fixed_input = pd.DataFrame([{
            "price": product["current_price"],
            "competitor_price": product["competitor_price"],
            "inventory": product["inventory"],
            "day_of_week": 2,
            "promotion": 0,
            "seasonal_factor": 1.0
        }], columns=FEATURES)

        fixed_demand = max(
            0, float(model.predict(fixed_input)[0])
        )
        fixed_units = min(fixed_demand, product["inventory"])
        fixed_profit = (
            product["current_price"] - product["cost_price"]
        ) * fixed_units

        # Evaluate optimized dynamic price
        recommendation = optimize_price(product, model)
        dynamic_profit = recommendation["expected_profit"]

        total_fixed_profit += fixed_profit
        total_dynamic_profit += dynamic_profit

        print(f"\nProduct: {product['product_name']}")
        print(f"Fixed price: ₹{product['current_price']:.2f}")
        print(f"Dynamic price: ₹{recommendation['recommended_price']:.2f}")
        print(f"Fixed-price estimated profit: ₹{fixed_profit:.2f}")
        print(f"Dynamic-price estimated profit: ₹{dynamic_profit:.2f}")

    improvement = (
        (total_dynamic_profit - total_fixed_profit)
        / total_fixed_profit * 100
        if total_fixed_profit > 0
        else 0
    )

    print("\n" + "=" * 75)
    print(f"Total fixed-price estimated profit: ₹{total_fixed_profit:.2f}")
    print(f"Total dynamic-price estimated profit: ₹{total_dynamic_profit:.2f}")
    print(f"Estimated profit improvement: {improvement:.2f}%")


if __name__ == "__main__":
    evaluate_pricing()