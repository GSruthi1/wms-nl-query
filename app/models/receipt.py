from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Receipt(Base):
    """One inbound trailer/receipt event — arrival through put-away completion."""

    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carrier: Mapped[str] = mapped_column(String(50), index=True)
    po_number: Mapped[str] = mapped_column(String(30), index=True)
    arrival_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    # nullable: a receipt still mid-putaway hasn't completed yet
    put_away_complete_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pallet_count: Mapped[int] = mapped_column(Integer)
