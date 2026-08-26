"""Initial WMS schema: locations, items, inventory, picks, receipts, labor, audit_log.

Revision ID: 0001
Revises:
Create Date: 2026-08-26

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_code", sa.String(20), nullable=False, unique=True),
        sa.Column("zone", sa.String(10), nullable=False),
        sa.Column("aisle", sa.String(10), nullable=False),
        sa.Column("bay", sa.String(10), nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("temperature_zone", sa.String(20), nullable=False),
        sa.Column("capacity", sa.Integer, nullable=False),
    )
    op.create_index("ix_locations_location_code", "locations", ["location_code"])
    op.create_index("ix_locations_zone", "locations", ["zone"])
    op.create_index("ix_locations_temperature_zone", "locations", ["temperature_zone"])

    op.create_table(
        "items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sku", sa.String(20), nullable=False, unique=True),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("velocity_class", sa.String(1), nullable=False),
        sa.Column("temperature_class", sa.String(20), nullable=False),
        sa.Column("uom", sa.String(10), nullable=False, server_default="EA"),
        sa.Column("case_pack", sa.Integer, nullable=False, server_default="1"),
    )
    op.create_index("ix_items_sku", "items", ["sku"])
    op.create_index("ix_items_velocity_class", "items", ["velocity_class"])
    op.create_index("ix_items_temperature_class", "items", ["temperature_class"])

    op.create_table(
        "inventory",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("sku", sa.String(20), sa.ForeignKey("items.sku"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("lot_number", sa.String(30), nullable=False),
        sa.Column("expiry_date", sa.Date, nullable=True),
        sa.Column("receipt_date", sa.Date, nullable=False),
    )
    op.create_index("ix_inventory_location_id", "inventory", ["location_id"])
    op.create_index("ix_inventory_sku", "inventory", ["sku"])
    op.create_index("ix_inventory_expiry_date", "inventory", ["expiry_date"])
    op.create_index("ix_inventory_receipt_date", "inventory", ["receipt_date"])

    op.create_table(
        "picks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sku", sa.String(20), sa.ForeignKey("items.sku"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("picker_id", sa.String(20), nullable=False),
        sa.Column("ts", sa.DateTime, nullable=False),
        sa.Column("order_id", sa.String(30), nullable=False),
    )
    op.create_index("ix_picks_sku", "picks", ["sku"])
    op.create_index("ix_picks_location_id", "picks", ["location_id"])
    op.create_index("ix_picks_picker_id", "picks", ["picker_id"])
    op.create_index("ix_picks_ts", "picks", ["ts"])
    op.create_index("ix_picks_order_id", "picks", ["order_id"])

    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("carrier", sa.String(50), nullable=False),
        sa.Column("po_number", sa.String(30), nullable=False),
        sa.Column("arrival_time", sa.DateTime, nullable=False),
        sa.Column("put_away_complete_time", sa.DateTime, nullable=True),
        sa.Column("pallet_count", sa.Integer, nullable=False),
    )
    op.create_index("ix_receipts_carrier", "receipts", ["carrier"])
    op.create_index("ix_receipts_po_number", "receipts", ["po_number"])
    op.create_index("ix_receipts_arrival_time", "receipts", ["arrival_time"])

    op.create_table(
        "labor",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("employee_id", sa.String(20), nullable=False),
        sa.Column("shift_date", sa.Date, nullable=False),
        sa.Column("zone", sa.String(10), nullable=False),
        sa.Column("picks_per_hour", sa.Float, nullable=False),
        sa.Column("dock_to_stock_minutes", sa.Float, nullable=False),
    )
    op.create_index("ix_labor_employee_id", "labor", ["employee_id"])
    op.create_index("ix_labor_shift_date", "labor", ["shift_date"])
    op.create_index("ix_labor_zone", "labor", ["zone"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ts", sa.DateTime, nullable=False),
        sa.Column("user_question", sa.Text, nullable=False),
        sa.Column("generated_sql", sa.Text, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("validation_passed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("execution_success", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("llm_provider", sa.String(20), nullable=True),
    )
    op.create_index("ix_audit_log_ts", "audit_log", ["ts"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("labor")
    op.drop_table("receipts")
    op.drop_table("picks")
    op.drop_table("inventory")
    op.drop_table("items")
    op.drop_table("locations")
