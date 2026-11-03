"""
Tests for restock order API endpoints.
"""
from datetime import datetime

import pytest


@pytest.fixture
def sample_restock_order_request():
    """Sample valid restock order creation payload."""
    return {
        "budget": 1000.0,
        "items": [
            {
                "sku": "WDG-001",
                "name": "Industrial Widget Type A",
                "quantity": 10,
                "unit_cost": 18.5,
                "line_total": 185.0
            },
            {
                "sku": "GSK-203",
                "name": "High-Temperature Gasket",
                "quantity": 20,
                "unit_cost": 6.75,
                "line_total": 135.0
            }
        ]
    }


class TestRestockOrderEndpoints:
    """Test suite for restock-order-related endpoints."""

    def test_get_restock_orders_returns_list(self, client):
        """Test getting restock orders returns a list."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    def test_create_restock_order_success(self, client, sample_restock_order_request):
        """Test creating a valid restock order."""
        response = client.post("/api/restock-orders", json=sample_restock_order_request)
        assert response.status_code == 201

        data = response.json()
        assert "id" in data
        assert "order_number" in data
        assert data["status"] == "Submitted"
        assert data["lead_time_days"] == 14
        assert data["budget"] == sample_restock_order_request["budget"]

        expected_total = sum(item["line_total"] for item in sample_restock_order_request["items"])
        assert abs(data["total_cost"] - expected_total) < 0.01

        order_date = datetime.fromisoformat(data["order_date"])
        expected_delivery = datetime.fromisoformat(data["expected_delivery"])
        assert (expected_delivery - order_date).days == 14

    def test_create_restock_order_then_appears_in_get(self, client, sample_restock_order_request):
        """Test that a created restock order shows up in the GET list."""
        create_response = client.post("/api/restock-orders", json=sample_restock_order_request)
        assert create_response.status_code == 201
        created = create_response.json()

        get_response = client.get("/api/restock-orders")
        assert get_response.status_code == 200

        all_orders = get_response.json()
        order_ids = [order["id"] for order in all_orders]
        assert created["id"] in order_ids

    def test_create_restock_order_empty_items_rejected(self, client):
        """Test that an empty items list is rejected."""
        response = client.post("/api/restock-orders", json={"budget": 500.0, "items": []})
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data

    def test_create_restock_order_exceeds_budget_rejected(self, client):
        """Test that a total cost exceeding budget is rejected."""
        payload = {
            "budget": 50.0,
            "items": [
                {
                    "sku": "MTR-304",
                    "name": "Electric Motor 5HP",
                    "quantity": 1,
                    "unit_cost": 285.0,
                    "line_total": 285.0
                }
            ]
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data

    def test_restock_order_item_structure(self, client, sample_restock_order_request):
        """Test that restock order items have the expected fields and types."""
        response = client.post("/api/restock-orders", json=sample_restock_order_request)
        assert response.status_code == 201

        data = response.json()
        assert isinstance(data["items"], list)
        assert len(data["items"]) == len(sample_restock_order_request["items"])

        for item in data["items"]:
            assert "sku" in item
            assert "name" in item
            assert "quantity" in item
            assert "unit_cost" in item
            assert "line_total" in item
            assert isinstance(item["quantity"], int)
            assert isinstance(item["unit_cost"], (int, float))
            assert isinstance(item["line_total"], (int, float))
