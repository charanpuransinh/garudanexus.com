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
