from pathlib import Path
import math
import sqlite3

import pandas as pd
from flask import Flask, jsonify, render_template, request

from database.db import (
    initialize_database,
    seed_products,
    get_all_products,
    get_product,
    create_product,
    update_product,
    delete_product,
)

from services.demand_model import train_model
from services.pricing_optimizer import optimize_price

from services.analytics import (
    initialize_analytics,
    record_recommendations,
    get_recommendation_history,
    get_sales_analytics,
    compare_pricing_strategies,
    analyze_competitors,
    generate_business_insights,
)


# --------------------------------------------------
# APPLICATION SETUP
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)


# --------------------------------------------------
# DATABASE INITIALIZATION
# --------------------------------------------------

def initialize_app():
    """Initialize the database and seed the product catalogue."""
    initialize_database()
    seed_products()
    initialize_analytics()


# --------------------------------------------------
# MACHINE LEARNING MODEL INITIALIZATION
# --------------------------------------------------

model = None


def initialize_model():
    """
    Train the demand prediction model once during application startup.
    Support functions that return either a model or (model, metrics).
    """
    global model

    app.logger.info("Initializing demand prediction model...")

    trained_result = train_model()

    if isinstance(trained_result, tuple):
        if not trained_result:
            raise RuntimeError("Model training returned an empty result.")

        trained_model = trained_result[0]
    else:
        trained_model = trained_result

    if trained_model is None or not callable(
        getattr(trained_model, "predict", None)
    ):
        raise RuntimeError(
            "Model training did not return a valid prediction model."
        )

    model = trained_model

    app.logger.info("Demand prediction model initialized successfully.")


# Initialize the database and model when this module loads.
initialize_app()
initialize_model()


# --------------------------------------------------
# SHARED HELPERS
# --------------------------------------------------

def error_response(message, status=400):
    """Return a consistent JSON error response."""
    return jsonify({"error": str(message)}), status


def json_body():
    """Read and validate a JSON request body."""
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        raise ValueError("Request must contain a valid JSON object.")

    return data


def validate_number(value, name, minimum=None):
    """Validate that a value is a finite number within its allowed range."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be numeric.")

    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number.")

    if minimum is not None and number < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")

    return number


def require_model():
    """Ensure the trained model is available before making predictions."""
    if model is None:
        raise RuntimeError("The demand prediction model is not initialized.")

    return model


def predict_demand(product, price):
    """
    Predict demand using the feature names expected by demand_model.py.
    """
    active_model = require_model()

    features = pd.DataFrame(
        [{
            "price": float(price),
            "competitor_price": float(product["competitor_price"]),
            "inventory": int(product["inventory"]),
            "day_of_week": 2,
            "promotion": 0,
            "seasonal_factor": 1.0,
        }]
    )

    predicted = float(active_model.predict(features)[0])

    if not math.isfinite(predicted):
        raise ValueError("The model returned an invalid demand prediction.")

    # Demand must not be negative or exceed available inventory.
    return max(
        0.0,
        min(predicted, float(product["inventory"])),
    )


def calculate_metrics(product, price):
    """Calculate estimated revenue, cost, and profit at a given price."""
    price = float(price)
    demand = predict_demand(product, price)
    cost_price = float(product["cost_price"])

    revenue = demand * price
    cost = demand * cost_price
    profit = revenue - cost

    return {
        "estimated_demand": round(demand, 2),
        "estimated_units_sold": round(demand, 2),
        "estimated_revenue": round(revenue, 2),
        "estimated_cost": round(cost, 2),
        "estimated_profit": round(profit, 2),
    }


def calculate_profit_change(current_profit, recommended_profit):
    """Calculate absolute and percentage changes in estimated profit."""
    change = recommended_profit - current_profit

    if current_profit != 0:
        change_percent = (change / abs(current_profit)) * 100
    else:
        change_percent = 0.0

    return {
        "estimated_profit_change": round(change, 2),
        "estimated_profit_change_percent": round(change_percent, 2),
    }


def get_recommendations_with_baseline():
    """
    Generate recommended prices and compare them with current-price
    estimates using the already-trained model.
    """
    require_model()

    results = []

    for product in get_all_products():
        recommendation = optimize_price(product, model)

        # Preserve product identity and current price.
        recommendation.setdefault(
            "product_id",
            product["product_id"],
        )
        recommendation.setdefault(
            "product_name",
            product["product_name"],
        )
        recommendation.setdefault(
            "current_price",
            product["current_price"],
        )

        recommended_price = float(
            recommendation.get(
                "recommended_price",
                product["current_price"],
            )
        )

        current_metrics = calculate_metrics(
            product,
            float(product["current_price"]),
        )

        dynamic_metrics = calculate_metrics(
            product,
            recommended_price,
        )

        current_profit = current_metrics["estimated_profit"]
        dynamic_profit = dynamic_metrics["estimated_profit"]

        profit_change = calculate_profit_change(
            current_profit,
            dynamic_profit,
        )

        # Provide consistent fields to the dashboard and analytics.
        recommendation.update({
            "current_expected_revenue":
                current_metrics["estimated_revenue"],

            "current_expected_profit":
                current_profit,

            "estimated_revenue":
                dynamic_metrics["estimated_revenue"],

            "estimated_profit":
                dynamic_profit,

            "estimated_demand":
                dynamic_metrics["estimated_demand"],

            "estimated_units_sold":
                dynamic_metrics["estimated_units_sold"],

            "estimated_cost":
                dynamic_metrics["estimated_cost"],

            **profit_change,
        })

        results.append(recommendation)

    return results


# --------------------------------------------------
# PAGE ROUTE
# --------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok" if model is not None else "error",
        "application": "PricePilot",
        "model_loaded": model is not None,
    }), (200 if model is not None else 503)


# --------------------------------------------------
# FEATURE 1: PRODUCT MANAGEMENT
# --------------------------------------------------

@app.route("/api/products", methods=["GET"])
def list_products():
    return jsonify(get_all_products())


@app.route("/api/products", methods=["POST"])
def add_product():
    try:
        data = json_body()
        product = create_product(data)

        return jsonify({
            "message": "Product created successfully.",
            "product": product,
        }), 201

    except ValueError as exc:
        return error_response(exc)

    except sqlite3.IntegrityError:
        return error_response(
            "A product with this ID already exists.",
            409,
        )


@app.route("/api/products/<product_id>", methods=["PUT", "PATCH"])
def edit_product(product_id):
    try:
        data = json_body()
        product = update_product(product_id, data)

        if product is None:
            return error_response("Product not found.", 404)

        return jsonify({
            "message": "Product updated successfully.",
            "product": product,
        })

    except ValueError as exc:
        return error_response(exc)

    except sqlite3.IntegrityError as exc:
        return error_response(
            f"Product update conflicts with database constraints: {exc}",
            400,
        )


@app.route("/api/products/<product_id>", methods=["DELETE"])
def remove_product(product_id):
    if not get_product(product_id):
        return error_response("Product not found.", 404)

    deleted = delete_product(product_id)

    if not deleted:
        return error_response("Product could not be deleted.", 404)

    return jsonify({
        "message": "Product deleted successfully.",
        "product_id": product_id,
    })


# --------------------------------------------------
# PRICING RECOMMENDATIONS
# --------------------------------------------------

@app.route("/api/recommendations", methods=["GET"])
def recommendations():
    try:
        return jsonify(get_recommendations_with_baseline())

    except Exception as exc:
        app.logger.exception("Recommendation generation failed")

        return error_response(
            f"Could not generate recommendations: {exc}",
            500,
        )


@app.route("/api/recommend/<product_id>", methods=["GET"])
def recommend_product(product_id):
    product = get_product(product_id)

    if not product:
        return error_response("Product not found.", 404)

    try:
        require_model()

        recommendation = optimize_price(product, model)

        current_metrics = calculate_metrics(
            product,
            float(product["current_price"]),
        )

        recommended_price = float(
            recommendation.get(
                "recommended_price",
                product["current_price"],
            )
        )

        dynamic_metrics = calculate_metrics(
            product,
            recommended_price,
        )

        profit_change = calculate_profit_change(
            current_metrics["estimated_profit"],
            dynamic_metrics["estimated_profit"],
        )

        recommendation.update({
            "product_id": product["product_id"],
            "product_name": product["product_name"],
            "current_price": float(product["current_price"]),

            "current_expected_revenue":
                current_metrics["estimated_revenue"],

            "current_expected_profit":
                current_metrics["estimated_profit"],

            "estimated_revenue":
                dynamic_metrics["estimated_revenue"],

            "estimated_profit":
                dynamic_metrics["estimated_profit"],

            "estimated_demand":
                dynamic_metrics["estimated_demand"],

            "estimated_units_sold":
                dynamic_metrics["estimated_units_sold"],

            "estimated_cost":
                dynamic_metrics["estimated_cost"],

            **profit_change,
        })

        return jsonify(recommendation)

    except Exception as exc:
        app.logger.exception("Single-product recommendation failed")
        return error_response(str(exc), 500)


# --------------------------------------------------
# FEATURE 2: SALES ANALYTICS
# --------------------------------------------------

@app.route("/api/analytics", methods=["GET"])
def analytics():
    try:
        return jsonify(get_sales_analytics())

    except (ValueError, FileNotFoundError) as exc:
        return error_response(exc, 400)

    except Exception as exc:
        app.logger.exception("Sales analytics failed")

        return error_response(
            f"Could not calculate sales analytics: {exc}",
            500,
        )


# --------------------------------------------------
# FEATURE 3: FIXED VS DYNAMIC PRICING
# --------------------------------------------------

@app.route("/api/pricing-comparison", methods=["GET"])
def pricing_comparison():
    try:
        results = get_recommendations_with_baseline()

        return jsonify(
            compare_pricing_strategies(results)
        )

    except Exception as exc:
        app.logger.exception("Pricing comparison failed")

        return error_response(
            f"Could not compare pricing strategies: {exc}",
            500,
        )


# --------------------------------------------------
# FEATURE 4: PERSISTENT RECOMMENDATION HISTORY
# --------------------------------------------------

@app.route("/api/recommendation-history", methods=["GET"])
def recommendation_history():
    try:
        limit = request.args.get(
            "limit",
            default=100,
            type=int,
        )

        if limit is None:
            return error_response("limit must be an integer.")

        if limit < 1:
            return error_response("limit must be at least 1.")

        return jsonify(get_recommendation_history(limit))

    except (ValueError, TypeError) as exc:
        return error_response(exc)

    except Exception as exc:
        app.logger.exception("History retrieval failed")

        return error_response(
            f"Could not retrieve recommendation history: {exc}",
            500,
        )


@app.route("/api/recommendation-history", methods=["POST"])
def save_recommendation_history():
    try:
        # Generate and save a snapshot only when explicitly requested.
        results = get_recommendations_with_baseline()

        if not results:
            return error_response(
                "There are no recommendations to save.",
                400,
            )

        record_recommendations(results)

        return jsonify({
            "message": "Recommendation snapshot saved successfully.",
            "products_saved": len(results),
        }), 201

    except Exception as exc:
        app.logger.exception(
            "Saving recommendation history failed"
        )

        return error_response(
            f"Could not save recommendation history: {exc}",
            500,
        )


# --------------------------------------------------
# FEATURE 5: COMPETITOR PRICE ANALYSIS
# --------------------------------------------------

@app.route("/api/competitors", methods=["GET"])
def competitor_analysis():
    try:
        current_products = get_all_products()
        results = get_recommendations_with_baseline()

        return jsonify(
            analyze_competitors(current_products, results)
        )

    except Exception as exc:
        app.logger.exception("Competitor analysis failed")

        return error_response(
            f"Could not analyse competitor prices: {exc}",
            500,
        )


# --------------------------------------------------
# FEATURE 6: BUSINESS INSIGHTS
# --------------------------------------------------

@app.route("/api/insights", methods=["GET"])
def business_insights():
    try:
        current_products = get_all_products()
        results = get_recommendations_with_baseline()

        return jsonify(
            generate_business_insights(current_products, results)
        )

    except Exception as exc:
        app.logger.exception("Business insights generation failed")

        return error_response(
            f"Could not generate business insights: {exc}",
            500,
        )


# --------------------------------------------------
# PRICE SIMULATOR
# --------------------------------------------------

@app.route("/api/simulate", methods=["POST"])
def simulate_price():
    try:
        data = json_body()

        product_id = str(
            data.get("product_id", "")
        ).strip()

        if not product_id:
            return error_response("product_id is required.")

        product = get_product(product_id)

        if not product:
            return error_response("Product not found.", 404)

        price = validate_number(
            data.get("price"),
            "price",
            minimum=0.01,
        )

        min_price = float(product["min_price"])
        max_price = float(product["max_price"])

        if price < min_price:
            return error_response(
                f"Price cannot be below the minimum of {min_price}."
            )

        if price > max_price:
            return error_response(
                f"Price cannot exceed the maximum of {max_price}."
            )

        metrics = calculate_metrics(product, price)

        return jsonify({
            "product_id": product_id,
            "product_name": product["product_name"],
            "price": price,
            **metrics,
        })

    except ValueError as exc:
        return error_response(exc)

    except Exception as exc:
        app.logger.exception("Price simulation failed")

        return error_response(
            f"Could not simulate price: {exc}",
            500,
        )


# --------------------------------------------------
# START APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
        use_reloader=False,
    )
