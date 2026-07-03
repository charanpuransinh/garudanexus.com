from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PartyCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=150,
        description="Customer or supplier name",
    )
    gstin: Optional[str] = Field(
        default=None,
        min_length=15,
        max_length=15,
        description="15-character GSTIN",
    )
    party_type: Literal["Customer", "Supplier"]
    balance: float = Field(default=0.0, ge=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Party name cannot be empty")
        return value

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None

        value = value.strip().upper()

        if len(value) != 15:
            raise ValueError("GSTIN must be exactly 15 characters")

        return value


class PartyRead(BaseModel):
    id: int
    name: str
    gstin: Optional[str]
    party_type: Literal["Customer", "Supplier"]
    balance: float

    model_config = ConfigDict(from_attributes=True)


class ProductCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Product name",
    )
    hsn: Optional[str] = Field(
        default=None,
        min_length=4,
        max_length=20,
        description="HSN code",
    )
    buy_price: float = Field(default=0.0, ge=0)
    sell_price: float = Field(default=0.0, ge=0)
    gst_rate: float = Field(default=0.0, ge=0, le=100)
    stock_qty: float = Field(default=0.0, ge=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Product name cannot be empty")
        return value

    @field_validator("hsn")
    @classmethod
    def validate_hsn(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None

        value = value.strip()

        if not value.isdigit():
            raise ValueError("HSN code must contain only numbers")

        return value


class ProductRead(BaseModel):
    id: int
    name: str
    hsn: Optional[str]
    buy_price: float
    sell_price: float
    gst_rate: float
    stock_qty: float

    model_config = ConfigDict(from_attributes=True)
