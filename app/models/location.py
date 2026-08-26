from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Location(Base):
    """A physical storage slot: zone/aisle/bay/level, e.g. FRZ-A-12-3."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    zone: Mapped[str] = mapped_column(String(10), index=True)
    aisle: Mapped[str] = mapped_column(String(10))
    bay: Mapped[str] = mapped_column(String(10))
    level: Mapped[str] = mapped_column(String(10))
    # ambient / chilled / frozen — must be consistent with any item stored
    # here (see Inventory), used for slotting/temperature-compliance questions
    temperature_zone: Mapped[str] = mapped_column(String(20), index=True)
    capacity: Mapped[int] = mapped_column(Integer)
