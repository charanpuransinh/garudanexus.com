from sqlalchemy import CheckConstraint, Column, Float, Integer, String
from database import Base


class Party(Base):
    __tablename__ = "parties"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    gstin = Column(String(15), nullable=True, unique=True, index=True)
    party_type = Column(String(20), nullable=False, index=True)
    balance = Column(Float, nullable=False, default=0.0)

    __table_args__ = (
        CheckConstraint(
            "party_type IN ('Customer', 'Supplier')",
            name="check_party_type",
        ),
    )

    def __repr__(self):
        return (
            f"<Party(id={self.id}, name='{self.name}', "
            f"party_type='{self.party_type}', balance={self.balance})>"
        )


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    hsn = Column(String(20), nullable=True, index=True)
    buy_price = Column(Float, nullable=False, default=0.0)
    sell_price = Column(Float, nullable=False, default=0.0)
    gst_rate = Column(Float, nullable=False, default=0.0)
    stock_qty = Column(Float, nullable=False, default=0.0)

    __table_args__ = (
        CheckConstraint("buy_price >= 0", name="check_buy_price_positive"),
        CheckConstraint("sell_price >= 0", name="check_sell_price_positive"),
        CheckConstraint("gst_rate >= 0", name="check_gst_rate_positive"),
        CheckConstraint("stock_qty >= 0", name="check_stock_qty_positive"),
    )

    def __repr__(self):
        return (
            f"<Product(id={self.id}, name='{self.name}', "
            f"stock_qty={self.stock_qty}, sell_price={self.sell_price})>"
        )
