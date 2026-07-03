from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import crud
import schemas
from database import get_db

router = APIRouter(
    prefix="/products",
    tags=["Products"]
)


@router.post(
    "/",
    response_model=schemas.ProductRead,
    status_code=status.HTTP_201_CREATED
)
def create_product(
    product: schemas.ProductCreate,
    db: Session = Depends(get_db)
):
    if product.stock_qty < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="stock_qty cannot be negative."
        )

    try:
        return crud.create_product(db=db, product=product)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product could not be created. Please check the product details."
        )


@router.get(
    "/",
    response_model=list[schemas.ProductRead],
    status_code=status.HTTP_200_OK
)
def get_all_products(db: Session = Depends(get_db)):
    return crud.get_products(db=db)
