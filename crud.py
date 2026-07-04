from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

import models
import schemas


# -------------------- Party Functions --------------------

def create_party(db: Session, party: schemas.PartyCreate):
    db_party = models.Party(**party.model_dump())
    db.add(db_party)
    db.commit()
    db.refresh(db_party)
    return db_party


def get_parties(db: Session):
    return db.query(models.Party).all()


# -------------------- Product Functions --------------------

def create_product(db: Session, product: schemas.ProductCreate):
    db_product = models.Product(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


def get_products(db: Session):
    return db.query(models.Product).all()


# -------------------- Transaction Functions --------------------

def create_bill(db: Session, bill: schemas.BillCreate):
    """
    Creates a bill, updates party balance, and adjusts product stock.

    Sales:
        - Product stock decreases
        - Party balance increases

    Purchase:
        - Product stock increases
        - Party balance decreases
    """
    try:
        party = db.query(models.Party).filter(
            models.Party.id == bill.party_id
        ).first()

        if not party:
            raise ValueError("Party not found.")

        product = db.query(models.Product).filter(
            models.Product.id == bill.product_id
        ).first()

        if not product:
            raise ValueError("Product not found.")

        if bill.qty <= 0:
            raise ValueError("Quantity must be greater than zero.")

        if bill.transaction_type not in ["sale", "purchase"]:
            raise ValueError("Transaction type must be either 'sale' or 'purchase'.")

        if bill.transaction_type == "sale":
            if product.stock_qty < bill.qty:
                raise ValueError("Insufficient product stock for this sale.")

            product.stock_qty -= bill.qty
            party.balance += bill.total_amount

        elif bill.transaction_type == "purchase":
            product.stock_qty += bill.qty
            party.balance -= bill.total_amount

        db_bill = models.Bill(**bill.model_dump())

        db.add(db_bill)
        db.commit()
        db.refresh(db_bill)

        return db_bill

    except Exception:
        db.rollback()
        raise


def create_quotation(db: Session, quotation: schemas.QuotationCreate):
    """
    Creates a quotation only.
    Party balance and product stock are not updated.
    """
    try:
        db_quotation = models.Quotation(**quotation.model_dump())

        db.add(db_quotation)
        db.commit()
        db.refresh(db_quotation)

        return db_quotation

    except SQLAlchemyError:
        db.rollback()
        raise
