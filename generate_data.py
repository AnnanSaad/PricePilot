import numpy as np
import pandas as pd

# Make the generated dataset reproducible
np.random.seed(42)

# Load our product catalogue
products = pd.read_csv("data/products.csv")

sales_records = []

# Generate 180 days of sample sales for every product
for _, product in products.iterrows():
    for day in range(180):

        # Simulate daily price variations around the current price
        price = np.random.uniform(
                product["min_price"],
                product["max_price"]
        )

        # Simulate inventory availability
        inventory = np.random.randint(
            max(1, int(product["inventory"] * 0.3)),
            int(product["inventory"]) + 1
        )

        # Simulate competitor price variations
        competitor_price = (
            product["competitor_price"] * np.random.uniform(0.95, 1.05)
        )

        # Day of the week: Monday = 0, Sunday = 6
        day_of_week = day % 7

        # Simulate occasional promotions
        promotion = np.random.choice([0, 1], p=[0.8, 0.2])

        # Products may sell more during certain periods
        seasonal_factor = np.random.uniform(0.85, 1.20)

        # Estimate demand using a synthetic demand relationship
        price_ratio = price / product["current_price"]

        expected_demand = (
            35
            * (price_ratio ** -1.8)
            * (1.15 if promotion else 1.0)
            * seasonal_factor
        )

        # Competitor pricing influences customer demand
        if price < competitor_price:
            expected_demand *= 1.10

        # Add random variation to simulate real-world uncertainty
        units_sold = int(
            max(0, np.random.normal(expected_demand, expected_demand * 0.15))
        )

        # Sales cannot exceed available inventory
        units_sold = min(units_sold, inventory)

        sales_records.append({
            "product_id": product["product_id"],
            "day": day,
            "price": round(price, 2),
            "competitor_price": round(competitor_price, 2),
            "inventory": inventory,
            "day_of_week": day_of_week,
            "promotion": promotion,
            "seasonal_factor": round(seasonal_factor, 2),
            "units_sold": units_sold
        })

# Save the generated records
sales_data = pd.DataFrame(sales_records)

sales_data.to_csv("data/sales_history.csv", index=False)

print("Sales dataset generated successfully!")
print(f"Total records: {len(sales_data)}")
print("\nFirst five records:")
print(sales_data.head())
