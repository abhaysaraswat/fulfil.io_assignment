"""Tests for product CRUD operations."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_list_products():
    """Test listing products with pagination."""
    response = client.get("/api/products")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "pages" in data


def test_create_product():
    """Test creating a new product."""
    product_data = {
        "sku": "TEST-SKU-001",
        "name": "Test Product",
        "description": "This is a test product",
        "active": True,
    }
    response = client.post("/api/products", json=product_data)
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == product_data["sku"].lower()
    assert data["name"] == product_data["name"]


def test_create_duplicate_sku():
    """Test that duplicate SKUs are rejected (case-insensitive)."""
    product_data = {
        "sku": "DUPLICATE-SKU",
        "name": "First Product",
        "description": "First product with this SKU",
        "active": True,
    }
    # Create first product
    response = client.post("/api/products", json=product_data)
    assert response.status_code == 201

    # Try to create second product with same SKU (different case)
    product_data["sku"] = "duplicate-sku"  # lowercase
    product_data["name"] = "Second Product"
    response = client.post("/api/products", json=product_data)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


def test_search_products():
    """Test searching products by SKU and name."""
    # Search by SKU
    response = client.get("/api/products?search=TEST")
    assert response.status_code == 200

    # Search by name
    response = client.get("/api/products?search=Product")
    assert response.status_code == 200


# Add more tests as needed:
# - test_update_product()
# - test_delete_product()
# - test_bulk_delete()
# - test_filter_by_active()
# - test_pagination()
