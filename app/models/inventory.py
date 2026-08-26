from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Inventory(Base):
    """On-hand inventory: one row per lot of a SKU sitting in a location."""

    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    sku: Mapped[str] = mapped_column(ForeignKey("items.sku"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    lot_number: Mapped[str] = mapped_column(String(30))
    # nullable: not every SKU is lot/expiry tracked (e.g. ambient dry goods)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    receipt_date: Mapped[date] = mapped_column(Date, index=True)
