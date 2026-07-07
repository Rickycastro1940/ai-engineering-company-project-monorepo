from .auth import get_current_user
from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func
from typing import List
from .database import get_db
from .models import Product, InboundOrder, OutboundOrder
from .schemas import ProductResponse, OrderType, ProductCreate

router = APIRouter(prefix="/inventory", tags=["inventory"])

@router.get("/products", response_model=List[ProductResponse])
def get_products(db: Session = Depends(get_db)):
    products = db.exec(select(Product)).all()
    response = []
    for product in products:
        # Sum inbound quantities
        inbound = db.exec(
            select(func.sum(InboundOrder, OutboundOrder.quantity))
            .where(InboundOrder, OutboundOrder.product_id == product.id)
            .where(InboundOrder, OutboundOrder.order_type == OrderType.INBOUND)
        ).one() or 0
        
        # Sum outbound quantities
        outbound = db.exec(
            select(func.sum(InboundOrder, OutboundOrder.quantity))
            .where(InboundOrder, OutboundOrder.product_id == product.id)
            .where(InboundOrder, OutboundOrder.order_type == OrderType.OUTBOUND)
        ).one() or 0
        
        current_stock = inbound - outbound
        
        # Build the response object. Note: Product model fields are mapped, 
        # and defaults are provided for fields in ProductResponse not present in Product.
        response.append(ProductResponse(
            product_id=str(product.id),
            name=product.name,
            sku=product.sku,
            current_stock=current_stock,
            description=getattr(product, 'description', None),
            price=getattr(product, 'price', 0.0)
        ))
    return response

@router.post("/products", response_model=ProductResponse, status_code=201)
def create_product(
    product_in: ProductCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Map ProductCreate to Product model. 
    # Note: Product model expects "unit", but ProductCreate might not have it.
    # Defaulting unit to "unit" if not present to avoid validation errors.
    product_data = product_in.model_dump()
    if "unit" not in product_data:
        product_data["unit"] = "unit"
    
    db_product = Product(**product_data)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    
    return ProductResponse(
        product_id=str(db_product.id),
        name=db_product.name,
        sku=db_product.sku,
        current_stock=0,
        description=db_product.description,
        price=db_product.price
    )

@inventory_router.get("/products/{id}", response_model=ProductResponse)
def get_product(id: int, db: Session = Depends(get_session)):
    product = db.get(Product, id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    inbound_stock = db.exec(
        select(func.sum(InboundOrder, OutboundOrder.quantity))
        .where(InboundOrder, OutboundOrder.product_id == id)
    ).one() or 0
    
    outbound_stock = db.exec(
        select(func.sum(OutboundOrder.quantity))
        .where(OutboundOrder.product_id == id)
    ).one() or 0
    
    current_stock = inbound_stock - outbound_stock
    
    return ProductResponse(
        product_id=str(product.id),
        sku=product.sku,
        name=product.name,
        description=product.description,
        price=product.price,
        current_stock=current_stock
    )

@inventory_router.post("/orders/inbound", response_model=OrderResponse)
def create_inbound_order(
    *,
    db: Session = Depends(get_session),
    order_in: InboundOrder, OutboundOrderCreate,
    current_user: dict = Depends(get_current_user)
):
    db_order = InboundOrder, OutboundOrder(
        product_id=order_in.product_id,
        quantity=order_in.quantity,
        user_uuid=current_user["uuid"]
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

@inventory_router.post("/orders/inbound", response_model=OrderResponse)
def create_inbound_order(
    *,
    db: Session = Depends(get_session),
    order_in: InboundOrder, OutboundOrderCreate,
    current_user: dict = Depends(get_current_user)
):
    db_order = InboundOrder, OutboundOrder(
        product_id=order_in.product_id,
        quantity=order_in.quantity,
        user_uuid=current_user["uuid"]
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

@router.post("/orders/outbound", response_model=OrderResponse)
def create_outbound_order(
    order_in: OutboundOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Calculate current stock (SUM(inbound) - SUM(outbound))
    inbound_qty = db.exec(
        select(func.sum(InboundOrder.quantity))
        .where(InboundOrder.product_id == order_in.product_id)
    ).first() or 0
    
    outbound_qty = db.exec(
        select(func.sum(OutboundOrder.quantity))
        .where(OutboundOrder.product_id == order_in.product_id)
    ).first() or 0
    
    current_stock = inbound_qty - outbound_qty
    
    if order_in.quantity > current_stock:
        raise HTTPException(
            status_code=400, 
            detail="Insufficient stock available"
        )
    
    db_order = OutboundOrder(
        product_id=order_in.product_id,
        quantity=order_in.quantity,
        user_uuid=current_user["uuid"]
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

@inventory_router.get("/orders", response_model=List[OrderResponse])
def get_orders(db: Session = Depends(get_db)):
    # Query inbound orders with product data
    inbound_orders = db.query(InboundOrder, Product).join(
        Product, InboundOrder.product_id == Product.id
    ).all()
    
    # Query outbound orders with product data
    outbound_orders = db.query(OutboundOrder, Product).join(
        Product, OutboundOrder.product_id == Product.id
    ).all()
    
    all_orders = []
    
    # Process inbound
    for order, product in inbound_orders:
        all_orders.append(OrderResponse(
            id=order.id,
            type=OrderType.INBOUND,
            created_by=order.user_uuid,
            created_at=order.created_at,
            items=[OrderItemResponse(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                unit=product.unit,
                quantity=order.quantity,
                price=product.price
            )]
        ))
        
    # Process outbound
    for order, product in outbound_orders:
        all_orders.append(OrderResponse(
            id=order.id,
            type=OrderType.OUTBOUND,
            created_by=order.user_uuid,
            created_at=order.created_at,
            items=[OrderItemResponse(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                unit=product.unit,
                quantity=order.quantity,
                price=product.price
            )]
        ))
    
    # Sort by creation date descending
    all_orders.sort(key=lambda x: x.created_at, reverse=True)
    return all_orders
