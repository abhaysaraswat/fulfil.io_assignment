"""Product CRUD API endpoints."""
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.product import Product
from app.schemas.product import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)
from app.services.webhook_service import trigger_webhooks

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
def list_products(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    sku: Optional[str] = Query(None, description="Filter by SKU (case-insensitive)"),
    name: Optional[str] = Query(None, description="Filter by name (partial match)"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search in SKU and name"),
    db: Session = Depends(get_db),
):
    """
    List products with pagination and filtering.

    Query Parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 50, max: 100)
    - sku: Filter by exact SKU (case-insensitive)
    - name: Filter by name (partial match, case-insensitive)
    - active: Filter by active status
    - search: Search in both SKU and name
    """
    query = db.query(Product)

    # Apply filters
    if sku:
        query = query.filter(func.lower(Product.sku) == sku.lower())
    if name:
        query = query.filter(Product.name.ilike(f"%{name}%"))
    if active is not None:
        query = query.filter(Product.active == active)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Product.sku.ilike(search_term),
                Product.name.ilike(search_term),
            )
        )

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    items = query.order_by(Product.created_at.desc()).offset(offset).limit(page_size).all()

    # Calculate total pages
    pages = math.ceil(total / page_size) if total > 0 else 1

    return ProductListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=ProductResponse, status_code=201)
async def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    """
    Create a new product.

    SKU must be unique (case-insensitive).
    """
    # Check if SKU already exists (case-insensitive)
    existing = (
        db.query(Product)
        .filter(func.lower(Product.sku) == product.sku.lower())
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Product with SKU '{product.sku}' already exists",
        )

    # Create new product
    db_product = Product(
        sku=product.sku.strip().lower(),  # Normalize to lowercase
        name=product.name,
        description=product.description,
        active=product.active,
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    # Trigger webhooks
    await trigger_webhooks(
        "product.created",
        {
            "event": "product.created",
            "data": {
                "id": db_product.id,
                "sku": db_product.sku,
                "name": db_product.name,
                "description": db_product.description,
                "active": db_product.active,
            },
        },
        db,
    )

    return db_product


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Get a single product by ID."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return product


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int, product_update: ProductUpdate, db: Session = Depends(get_db)
):
    """
    Update a product.

    Only provided fields will be updated.
    """
    # Get existing product
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check if SKU is being updated and if it conflicts
    if product_update.sku is not None:
        sku_lower = product_update.sku.lower()
        existing = (
            db.query(Product)
            .filter(func.lower(Product.sku) == sku_lower)
            .filter(Product.id != product_id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Product with SKU '{product_update.sku}' already exists",
            )
        db_product.sku = sku_lower

    # Update other fields
    if product_update.name is not None:
        db_product.name = product_update.name
    if product_update.description is not None:
        db_product.description = product_update.description
    if product_update.active is not None:
        db_product.active = product_update.active

    db.commit()
    db.refresh(db_product)

    # Trigger webhooks
    await trigger_webhooks(
        "product.updated",
        {
            "event": "product.updated",
            "data": {
                "id": db_product.id,
                "sku": db_product.sku,
                "name": db_product.name,
                "description": db_product.description,
                "active": db_product.active,
            },
        },
        db,
    )

    return db_product


@router.delete("/{product_id}", status_code=204)
async def delete_product(product_id: int, db: Session = Depends(get_db)):
    """Delete a single product."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Store product data before deletion for webhook
    product_data = {
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
    }

    db.delete(product)
    db.commit()

    # Trigger webhooks
    await trigger_webhooks(
        "product.deleted",
        {"event": "product.deleted", "data": product_data},
        db,
    )

    return None


@router.delete("/bulk/all", response_model=dict)
def bulk_delete_products(db: Session = Depends(get_db)):
    """
    Delete all products (bulk delete).

    Returns the count of deleted products.
    """
    deleted_count = db.query(Product).delete()
    db.commit()

    return {"deleted_count": deleted_count}
