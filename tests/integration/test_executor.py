from app.models.item import Item
from app.models.location import Location
from app.nl2sql.executor import execute_sql


def test_execute_valid_select_returns_rows(db_session, readonly_db_session):
    db_session.add(Location(
        location_code="FRZ-A01-1", zone="FRZ", aisle="A", bay="01", level="1",
        temperature_zone="frozen", capacity=24,
    ))
    db_session.add(Item(
        sku="SKU-TEST01", description="Test Item", velocity_class="A",
        temperature_class="frozen", uom="EA", case_pack=1,
    ))
    db_session.commit()

    result = execute_sql(readonly_db_session, "SELECT sku, velocity_class FROM items")
    assert result.success
    assert result.row_count == 1
    assert result.rows[0]["sku"] == "SKU-TEST01"


def test_execute_invalid_sql_returns_error_not_exception(readonly_db_session):
    result = execute_sql(readonly_db_session, "SELECT nonexistent_column FROM items")
    assert not result.success
    assert result.error is not None
