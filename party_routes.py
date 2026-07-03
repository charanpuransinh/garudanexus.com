from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import crud
import schemas
from database import get_db


router = APIRouter(
    prefix="/parties",
    tags=["Parties"],
)


@router.post(
    "/",
    response_model=schemas.PartyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_party(
    party: schemas.PartyCreate,
    db: Session = Depends(get_db),
):
    try:
        return crud.create_party(db=db, party=party)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A party with this GSTIN already exists.",
        )


@router.get(
    "/",
    response_model=List[schemas.PartyRead],
)
def get_all_parties(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    if skip < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="skip cannot be negative.",
        )

    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be between 1 and 500.",
        )

    return crud.get_parties(db=db, skip=skip, limit=limit)
