from sqlalchemy.orm import Session

import models
import schemas


def create_party(db: Session, party: schemas.PartyCreate) -> models.Party:
    db_party = models.Party(
        name=party.name,
        gstin=party.gstin,
        party_type=party.party_type,
        balance=party.balance,
    )

    db.add(db_party)
    db.commit()
    db.refresh(db_party)

    return db_party


def get_parties(
    db: Session,
    skip: int = 0,
    limit: int = 100,
) -> list[models.Party]:
    return (
        db.query(models.Party)
        .order_by(models.Party.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_product(
    db: Session,
    product: schemas.ProductCreate,
) -> models.Product:
    db_product = models.Product(
        name=product.name,
        hsn=product.hsn,
        buy_price=product.buy_price,
        sell_price=product.sell_price,
        gst_rate=product.gst_rate,
        stock_qty=product.stock_qty,
    )

    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    return db_product


def get_products(
    db: Session,
    skip: int = 0,
    limit: int = 100,
) -> list[models.Product]:
    return (
        db.query(models.Product)
        .order_by(models.Product.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
