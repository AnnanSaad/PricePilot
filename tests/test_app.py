import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        yield test_client


def test_homepage_loads(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"PricePilot" in response.data


def test_product_catalogue_returns_six_products(client):
    response = client.get("/api/products")

    assert response.status_code == 200

    products = response.get_json()

    assert len(products) == 6
    assert all("product_id" in product for product in products)


def test_unknown_product_returns_404(client):
    response = client.get("/api/recommend/UNKNOWN")

    assert response.status_code == 404


def test_simulator_rejects_missing_fields(client):
    response = client.post(
        "/api/simulate",
        json={"product_id": "P1001"}
    )

    assert response.status_code == 400


def test_simulator_rejects_unknown_product(client):
    response = client.post(
        "/api/simulate",
        json={
            "product_id": "UNKNOWN",
            "price": 1800
        }
    )

    assert response.status_code == 404


def test_simulator_accepts_valid_request(client):
    response = client.post(
        "/api/simulate",
        json={
            "product_id": "P1001",
            "price": 1800
        }
    )

    assert response.status_code == 200

    result = response.get_json()

    assert result["price"] == 1800
    assert result["predicted_demand"] >= 0
    assert result["expected_revenue"] >= 0
    assert "expected_profit" in result
