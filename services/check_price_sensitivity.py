import pandas as pd

from services.demand_model import FEATURES, train_model


def check_price_sensitivity():
    products = pd.read_csv("data/products.csv")
    model = train_model()

    product = products.iloc[0]

    print("\nPRICE SENSITIVITY ANALYSIS")
    print("=" * 55)
    print(f"Product: {product['product_name']}")
    print("-" * 55)

    prices = [1400, 1600, 1800, 2000, 2200, 2400, 2600, 2800]

    for price in prices:
        input_data = pd.DataFrame([{
            "price": price,
            "competitor_price": product["competitor_price"],
            "inventory": product["inventory"],
            "day_of_week": 2,
            "promotion": 0,
            "seasonal_factor": 1.0
        }], columns=FEATURES)

        predicted_demand = model.predict(input_data)[0]

        profit = (
            price - product["cost_price"]
        ) * predicted_demand

        print(
            f"Price: ₹{price:<5} | "
            f"Demand: {predicted_demand:>6.2f} | "
            f"Profit: ₹{profit:>10.2f}"
        )


if __name__ == "__main__":
    check_price_sensitivity()