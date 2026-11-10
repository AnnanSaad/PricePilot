"""Analytics services for PricePilot."""

import sqlite3
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SALES_FILE = DATA_DIR / "sales_history.csv"
DB_FILE = DATA_DIR / "pricepilot.db"


# --------------------------------------------------
# DATABASE HELPERS
# --------------------------------------------------

def _connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row

    return connection


def initialize_analytics():
    """Create the recommendation history table if it does not exist."""

    with _connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS recommendation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                product_id TEXT NOT NULL,
                product_name TEXT,
                current_price REAL,
                recommended_price REAL,
                expected_profit REAL,
                estimated_profit_change REAL
            )
        """)

        connection.commit()


# --------------------------------------------------
# RECOMMENDATION HISTORY
# --------------------------------------------------

def record_recommendations(recommendations):
    """Save a snapshot of the current pricing recommendations."""

    initialize_analytics()

    rows = []

    for item in recommendations:
        rows.append((
            str(item.get("product_id", "")),
            str(item.get("product_name", "")),
            float(item.get("current_price", 0) or 0),
            float(item.get("recommended_price", 0) or 0),
            float(
                item.get(
                    "estimated_profit",
                    item.get("expected_profit", 0)
                ) or 0
            ),
            float(item.get("estimated_profit_change", 0) or 0),
        ))

    if not rows:
        return 0

    with _connect() as connection:
        connection.executemany("""
            INSERT INTO recommendation_history (
                product_id,
                product_name,
                current_price,
                recommended_price,
                expected_profit,
                estimated_profit_change
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, rows)

        connection.commit()

    return len(rows)


def get_recommendation_history(limit=100):
    """Retrieve recent recommendation snapshots."""

    initialize_analytics()

    limit = max(1, min(int(limit), 1000))

    with _connect() as connection:
        rows = connection.execute("""
            SELECT
                id,
                created_at,
                product_id,
                product_name,
                current_price,
                recommended_price,
                expected_profit,
                estimated_profit_change
            FROM recommendation_history
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [dict(row) for row in rows]


# --------------------------------------------------
# SALES ANALYTICS
# --------------------------------------------------

def get_sales_analytics():
    """
    Return daily and product-level revenue for the dashboard.

    Expected sales_history.csv columns include:
    product_id, day, price, units_sold
    """

    empty_result = {
        "daily": {
            "labels": [],
            "revenue": [],
            "units": [],
        },
        "products": {
            "labels": [],
            "revenue": [],
            "units": [],
        },
    }

    if not SALES_FILE.exists():
        return empty_result

    frame = pd.read_csv(SALES_FILE)

    required_columns = {
        "product_id",
        "price",
        "units_sold",
    }

    if not required_columns.issubset(frame.columns):
        return empty_result

    frame["price"] = pd.to_numeric(
        frame["price"],
        errors="coerce",
    )

    frame["units_sold"] = pd.to_numeric(
        frame["units_sold"],
        errors="coerce",
    )

    frame = frame.dropna(
        subset=["product_id", "price", "units_sold"]
    )

    frame["revenue"] = (
        frame["price"] * frame["units_sold"]
    )

    # Aggregate sales by numeric day.
    if "day" in frame.columns:
        frame["day"] = pd.to_numeric(
            frame["day"],
            errors="coerce",
        )

        daily = (
            frame.dropna(subset=["day"])
            .groupby("day")
            .agg(
                revenue=("revenue", "sum"),
                units=("units_sold", "sum"),
            )
            .sort_index()
        )

        daily_labels = [
            (
                f"Day {int(day)}"
                if float(day).is_integer()
                else str(day)
            )
            for day in daily.index
        ]

        daily_revenue = [
            round(float(value), 2)
            for value in daily["revenue"]
        ]

        daily_units = [
            round(float(value), 2)
            for value in daily["units"]
        ]

    else:
        daily_labels = []
        daily_revenue = []
        daily_units = []

    # Aggregate sales by product.
    product_sales = (
        frame.groupby("product_id")
        .agg(
            revenue=("revenue", "sum"),
            units=("units_sold", "sum"),
        )
        .sort_values("revenue", ascending=False)
    )

    product_labels = [
        str(product_id)
        for product_id in product_sales.index
    ]

    product_revenue = [
        round(float(value), 2)
        for value in product_sales["revenue"]
    ]

    product_units = [
        round(float(value), 2)
        for value in product_sales["units"]
    ]

    return {
        "daily": {
            "labels": daily_labels,
            "revenue": daily_revenue,
            "units": daily_units,
        },
        "products": {
            "labels": product_labels,
            "revenue": product_revenue,
            "units": product_units,
        },
    }


# --------------------------------------------------
# FIXED VS DYNAMIC PRICING COMPARISON
# --------------------------------------------------

def compare_pricing_strategies(recommendations):
    """
    Compare estimated profit at the current price with profit
    at the recommended price.

    app.py supplies:
    current_expected_profit = current-price baseline
    estimated_profit = recommended-price estimate
    """

    results = []

    for item in recommendations:
        current_price = float(
            item.get("current_price", 0) or 0
        )

        recommended_price = float(
            item.get("recommended_price", current_price)
            or current_price
        )

        fixed_value = item.get(
            "current_expected_profit",
            item.get("current_profit", item.get("fixed_profit")),
        )

        dynamic_value = item.get(
            "estimated_profit",
            item.get("expected_profit", item.get("dynamic_profit")),
        )

        fixed_profit = (
            float(fixed_value)
            if fixed_value is not None
            else None
        )

        dynamic_profit = (
            float(dynamic_value)
            if dynamic_value is not None
            else None
        )

        if (
            fixed_profit is not None
            and dynamic_profit is not None
        ):
            profit_change = round(
                dynamic_profit - fixed_profit,
                2,
            )
        else:
            profit_change = None

        results.append({
            "product_id": item.get("product_id"),
            "product_name": item.get(
                "product_name",
                item.get("name", ""),
            ),
            "current_price": current_price,
            "recommended_price": recommended_price,
            "fixed_profit": fixed_profit,
            "dynamic_profit": dynamic_profit,
            "profit_change": profit_change,
        })

    return results


# --------------------------------------------------
# COMPETITOR PRICE ANALYSIS
# --------------------------------------------------

def analyze_competitors(products, recommendations):
    """
    Compare current product prices against competitor prices.

    A negative gap means the current price is below the competitor.
    A positive gap means the current price is above the competitor.
    """

    recommendations_by_id = {
        str(item.get("product_id")): item
        for item in recommendations
    }

    results = []

    for product in products:
        product_id = str(
            product.get("product_id", "")
        )

        current_price = float(
            product.get("current_price", 0) or 0
        )

        competitor_price = float(
            product.get("competitor_price", 0) or 0
        )

        recommendation = recommendations_by_id.get(
            product_id,
            {},
        )

        recommended_price = float(
            recommendation.get(
                "recommended_price",
                current_price,
            ) or current_price
        )

        price_gap = round(
            current_price - competitor_price,
            2,
        )

        if competitor_price <= 0:
            position = "competitor price unavailable"
            price_gap_percent = None

        else:
            price_gap_percent = round(
                (price_gap / competitor_price) * 100,
                2,
            )

            if price_gap > 0:
                position = "above competitor"
            elif price_gap < 0:
                position = "below competitor"
            else:
                position = "at competitor price"

        results.append({
            "product_id": product_id,
            "product_name": product.get(
                "product_name",
                product.get("name", product_id),
            ),
            "current_price": current_price,
            "competitor_price": competitor_price,
            "recommended_price": recommended_price,
            "price_gap": price_gap,
            "price_gap_percent": price_gap_percent,
            "position": position,
        })

    return results


# --------------------------------------------------
# BUSINESS INSIGHTS
# --------------------------------------------------

def generate_business_insights(products=None, recommendations=None):
    """
    Generate basic business insights.

    Argument order matches app.py:
    generate_business_insights(current_products, recommendations)
    """

    products = products or []
    recommendations = recommendations or []

    if not recommendations:
        return [{
            "type": "neutral",
            "title": "No recommendations available",
            "message": (
                "Load the product catalogue and generate "
                "pricing recommendations first."
            ),
        }]

    total_change = sum(
        float(item.get("estimated_profit_change", 0) or 0)
        for item in recommendations
    )

    positive_count = sum(
        1
        for item in recommendations
        if float(
            item.get("estimated_profit_change", 0) or 0
        ) > 0
    )

    insights = [{
        "type": (
            "positive"
            if total_change >= 0
            else "negative"
        ),
        "title": "Estimated profit opportunity",
        "message": (
            f"The model estimates a combined profit change of "
            f"₹{total_change:,.2f} across "
            f"{len(recommendations)} products. "
            "This is a forecast, not a guarantee."
        ),
    }, {
        "type": (
            "positive"
            if positive_count > 0
            else "neutral"
        ),
        "title": "Products with positive estimates",
        "message": (
            f"{positive_count} of {len(recommendations)} products "
            "have a positive estimated profit change."
        ),
    }]

    below_cost = [
        product
        for product in products
        if float(product.get("current_price", 0) or 0)
        < float(product.get("cost_price", 0) or 0)
    ]

    if below_cost:
        insights.append({
            "type": "negative",
            "title": "Prices below cost",
            "message": (
                f"{len(below_cost)} product(s) currently have "
                "a selling price below cost."
            ),
        })

    return insights
