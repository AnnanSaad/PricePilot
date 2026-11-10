import math
import sqlite3
from pathlib import Path
from contextlib import contextmanager

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_FILE = BASE_DIR / "data" / "pricepilot.db"

PRODUCT_COLUMNS = [
    "product_id",
    "product_name",
    "current_price",
    "cost_price",
    "inventory",
    "competitor_price",
    "min_price",
    "max_price",
]

NUMERIC_COLUMNS = [
    "current_price",
    "cost_price",
    "inventory",
    "competitor_price",
    "min_price",
    "max_price",
]


@contextmanager
def get_connection():
    """Open a database connection and manage its lifecycle."""

    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_FILE, timeout=10)
    connection.row_factory = sqlite3.Row

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    """Create the products table if it does not exist."""

    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                current_price REAL NOT NULL CHECK (current_price > 0),
                cost_price REAL NOT NULL CHECK (cost_price >= 0),
                inventory INTEGER NOT NULL CHECK (inventory >= 0),
                competitor_price REAL NOT NULL CHECK (competitor_price >= 0),
                min_price REAL NOT NULL CHECK (min_price > 0),
                max_price REAL NOT NULL CHECK (max_price >= min_price)
            )
        """)


def validate_product(data, partial=False):
    """Validate product fields before database writes."""

    if not isinstance(data, dict):
        raise ValueError("Product data must be a JSON object.")

    allowed_fields = set(PRODUCT_COLUMNS)
    unexpected = set(data) - allowed_fields

    if unexpected:
        raise ValueError(
            f"Unexpected fields: {', '.join(sorted(unexpected))}"
        )

    # Partial updates validate only supplied fields.
    # Product creation requires every field.
    required_fields = set() if partial else set(PRODUCT_COLUMNS)

    missing = required_fields - set(data)

    if missing:
        raise ValueError(
            f"Missing fields: {', '.join(sorted(missing))}"
        )

    validated = {}

    if "product_id" in data:
        product_id = data["product_id"]

        if not isinstance(product_id, str) or not product_id.strip():
            raise ValueError("Product ID must be a non-empty string.")

        validated["product_id"] = product_id.strip()

    if "product_name" in data:
        name = data["product_name"]

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Product name must be a non-empty string.")

        validated["product_name"] = name.strip()

    for column in NUMERIC_COLUMNS:
        if column not in data:
            continue

        value = data[column]

        if isinstance(value, bool):
            raise ValueError(f"{column} must be numeric.")

        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"{column} must be numeric.")

        if not math.isfinite(number):
            raise ValueError(f"{column} must be finite.")

        if column == "inventory":
            if number < 0 or not number.is_integer():
                raise ValueError(
                    "Inventory must be a non-negative whole number."
                )

            number = int(number)

        validated[column] = number

    # Validate individual values for both creation and updates.
    if "current_price" in validated and validated["current_price"] <= 0:
        raise ValueError("Current price must be positive.")

    if "cost_price" in validated and validated["cost_price"] < 0:
        raise ValueError("Cost price cannot be negative.")

    if "inventory" in validated and validated["inventory"] < 0:
        raise ValueError("Inventory cannot be negative.")

    if (
        "competitor_price" in validated
        and validated["competitor_price"] < 0
    ):
        raise ValueError("Competitor price cannot be negative.")

    if "min_price" in validated and validated["min_price"] <= 0:
        raise ValueError("Minimum price must be positive.")

    if (
        "min_price" in validated
        and "max_price" in validated
        and validated["max_price"] < validated["min_price"]
    ):
        raise ValueError("Maximum price cannot be below minimum price.")

    if not partial:
        if not (
            validated["min_price"]
            <= validated["current_price"]
            <= validated["max_price"]
        ):
            raise ValueError(
                "Current price must be within the allowed price range."
            )

    return validated


def seed_products(csv_path=None):
    """Import initial products without overwriting existing records."""

    source = (
        Path(csv_path)
        if csv_path
        else BASE_DIR / "data" / "products.csv"
    )

    if not source.exists():
        raise FileNotFoundError(
            f"Product catalogue not found: {source}"
        )

    data = pd.read_csv(source)

    missing = set(PRODUCT_COLUMNS) - set(data.columns)

    if missing:
        raise ValueError(
            f"Product CSV is missing columns: "
            f"{', '.join(sorted(missing))}"
        )

    if data["product_id"].duplicated().any():
        raise ValueError("Product IDs must be unique.")

    records = []

    for _, row in data.iterrows():
        product = validate_product({
            column: row[column]
            for column in PRODUCT_COLUMNS
        })

        records.append(
            tuple(product[column] for column in PRODUCT_COLUMNS)
        )

    with get_connection() as connection:
        connection.executemany(
            """
            INSERT OR IGNORE INTO products (
                product_id,
                product_name,
                current_price,
                cost_price,
                inventory,
                competitor_price,
                min_price,
                max_price
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )


def get_all_products():
    """Return all products as a list of dictionaries."""

    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM products ORDER BY product_id"
        ).fetchall()

    return [dict(row) for row in rows]


def get_product(product_id):
    """Return one product, or None if it does not exist."""

    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM products WHERE product_id = ?",
            (product_id,),
        ).fetchone()

    return dict(row) if row else None


def create_product(data):
    """Validate and insert a new product."""

    product = validate_product(data)

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO products (
                product_id,
                product_name,
                current_price,
                cost_price,
                inventory,
                competitor_price,
                min_price,
                max_price
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(product[column] for column in PRODUCT_COLUMNS),
        )

    return get_product(product["product_id"])


def update_product(product_id, data):
    """Update supplied fields while preserving all unspecified fields."""

    existing = get_product(product_id)

    if existing is None:
        return None

    if not isinstance(data, dict) or not data:
        raise ValueError("Provide at least one field to update.")

    if "product_id" in data:
        if data["product_id"] != product_id:
            raise ValueError("Product ID cannot be changed.")

    validated = validate_product(data, partial=True)

    if not validated:
        raise ValueError("Provide at least one valid field to update.")

    updated = {**existing, **validated}

    # Validate the complete updated product and its price boundaries.
    updated = validate_product(updated)

    fields = [
        column
        for column in PRODUCT_COLUMNS
        if column != "product_id"
    ]

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE products
            SET product_name = ?,
                current_price = ?,
                cost_price = ?,
                inventory = ?,
                competitor_price = ?,
                min_price = ?,
                max_price = ?
            WHERE product_id = ?
            """,
            tuple(updated[column] for column in fields) + (product_id,),
        )

    return get_product(product_id)


def delete_product(product_id):
    """Delete a product and return True if it existed."""

    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM products WHERE product_id = ?",
            (product_id,),
        )

    return cursor.rowcount > 0


if __name__ == "__main__":
    initialize_database()
    seed_products()

    print(f"Database initialized: {DATABASE_FILE}")
    print(f"Products loaded: {len(get_all_products())}")
