from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Item(Base):
    """A SKU master record."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(200))
    # A/B/C ABC-velocity classification — A = fastest movers ("hot picks"
    # candidates). Drives slotting questions (should a C-class item be in a
    # golden/forward pick location?).
    velocity_class: Mapped[str] = mapped_column(String(1), index=True)
    # ambient / chilled / frozen
    temperature_class: Mapped[str] = mapped_column(String(20), index=True)
    uom: Mapped[str] = mapped_column(String(10), default="EA")
    case_pack: Mapped[int] = mapped_column(Integer, default=1)
