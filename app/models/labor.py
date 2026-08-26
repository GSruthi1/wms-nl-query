from datetime import date

from sqlalchemy import Date, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Labor(Base):
    """One employee-shift labor summary row."""

    __tablename__ = "labor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(20), index=True)
    shift_date: Mapped[date] = mapped_column(Date, index=True)
    zone: Mapped[str] = mapped_column(String(10), index=True)
    picks_per_hour: Mapped[float] = mapped_column(Float)
    dock_to_stock_minutes: Mapped[float] = mapped_column(Float)
