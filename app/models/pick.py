from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Pick(Base):
    """One outbound pick event: a picker pulled `quantity` of `sku` from a location."""

    __tablename__ = "picks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(ForeignKey("items.sku"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    picker_id: Mapped[str] = mapped_column(String(20), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    order_id: Mapped[str] = mapped_column(String(30), index=True)
