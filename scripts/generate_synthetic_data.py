"""
Generate realistic synthetic cold-chain WMS data and load it into Postgres.

Deliberately not uniform-random: distributions are skewed the way a real
cold-chain DC's data is, because that skew is what makes benchmark
questions like "what are our hot picks" or "which receipts blew dock-to-
stock SLA" have a real, non-trivial answer instead of a coin flip.

Reproducible via --seed (default 42, matching the LDIP project's own
synthetic-data convention). Re-running always TRUNCATEs the 6 WMS data
tables first (not audit_log — that's a real operational log, not seed
data) so the script is idempotent.

Usage:
    docker compose exec app python -m scripts.generate_synthetic_data
    docker compose exec app python -m scripts.generate_synthetic_data --seed 7 --picks 5000
"""
import argparse
import random
from datetime import date, datetime, time, timedelta

from faker import Faker
from sqlalchemy import insert, text

from app.db.session import engine
from app.models import Inventory, Item, Labor, Location, Pick, Receipt

# --- Curated domain vocabulary -----------------------------------------
# Real Faker word-salad reads as obviously fake for a food/cold-chain
# catalog ("Loyal Ergonomic Chicken"). Curated per-temperature-class product
# nouns read as a real DC's item master, which matters for a portfolio demo.
FROZEN_PRODUCTS = [
    "Chicken Breast", "Chicken Thighs", "Ground Beef 80/20", "Beef Patties",
    "Mixed Vegetables", "Green Peas", "French Fries", "Pizza Rounds",
    "Vanilla Ice Cream", "Shrimp 21/25", "Salmon Fillets", "Pork Chops",
    "Waffles", "Breaded Fish Sticks", "Corn Kernels", "Berry Blend",
]
CHILLED_PRODUCTS = [
    "Whole Milk", "2% Milk", "Heavy Cream", "Greek Yogurt", "String Cheese",
    "Cheddar Block", "Fresh Eggs", "Butter", "Deli Turkey", "Salsa",
    "Orange Juice", "Cottage Cheese", "Sour Cream", "Fresh Salsa",
    "Rotisserie Chicken", "Prepared Salad Mix",
]
AMBIENT_PRODUCTS = [
    "Canned Corn", "Canned Green Beans", "Pasta Sauce", "Spaghetti",
    "White Rice", "Black Beans (Canned)", "Cereal", "Peanut Butter",
    "Vegetable Oil", "Ketchup", "Crackers", "Granola Bars", "Coffee",
    "Bottled Water 24pk", "Paper Towels", "Canned Tuna",
]
PACK_SIZES = ["6ct", "12ct", "24ct", "1lb", "5lb", "10lb", "32oz", "64oz", "case"]

CARRIERS = [
    "Werner Reefer Logistics", "C.H. Robinson", "Prime Inc.", "Frozen Food Express",
    "Marten Transport", "KLLM Transport", "Estes Cold Chain", "Saddle Creek Logistics",
    "Lineage Transportation", "AGRO Merchants Freight",
]

TEMPERATURE_CLASSES = ["frozen", "chilled", "ambient"]
TEMPERATURE_WEIGHTS = [40, 35, 25]
VELOCITY_CLASSES = ["A", "B", "C"]
VELOCITY_WEIGHTS = [15, 30, 55]
# How much more likely an A/B/C item is to be picked, per pick event —
# this is the actual signal behind "hot picks" questions.
VELOCITY_PICK_WEIGHT = {"A": 10, "B": 3, "C": 1}

ZONE_PREFIX = {"frozen": "FRZ", "chilled": "CHL", "ambient": "AMB"}


def zone_products(temp_class: str) -> list[str]:
    return {"frozen": FROZEN_PRODUCTS, "chilled": CHILLED_PRODUCTS, "ambient": AMBIENT_PRODUCTS}[
        temp_class
    ]


def shelf_life_days(temp_class: str, rng: random.Random) -> int:
    """Rough real-world shelf life by temperature class."""
    if temp_class == "frozen":
        return rng.randint(180, 365)
    if temp_class == "chilled":
        return rng.randint(7, 45)
    return rng.randint(180, 730)


def generate_locations(rng: random.Random, count: int) -> list[dict]:
    locations = []
    counts_by_zone = {
        "frozen": int(count * 0.375),
        "chilled": int(count * 0.35),
    }
    counts_by_zone["ambient"] = count - counts_by_zone["frozen"] - counts_by_zone["chilled"]

    seen_codes: set[str] = set()
    for temp_class, n in counts_by_zone.items():
        prefix = ZONE_PREFIX[temp_class]
        for _ in range(n):
            while True:
                aisle = rng.choice("ABCDEFGHIJ")
                bay = f"{rng.randint(1, 24):02d}"
                level = str(rng.randint(1, 4))
                code = f"{prefix}-{aisle}{bay}-{level}"
                if code not in seen_codes:
                    seen_codes.add(code)
                    break
            locations.append(
                {
                    "location_code": code,
                    "zone": prefix,
                    "aisle": aisle,
                    "bay": bay,
                    "level": level,
                    "temperature_zone": temp_class,
                    "capacity": rng.choice([24, 36, 48, 60]),
                }
            )
    return locations


def generate_items(rng: random.Random, count: int) -> list[dict]:
    items = []
    used_descriptions: set[str] = set()
    for i in range(1, count + 1):
        temp_class = rng.choices(TEMPERATURE_CLASSES, weights=TEMPERATURE_WEIGHTS)[0]
        velocity = rng.choices(VELOCITY_CLASSES, weights=VELOCITY_WEIGHTS)[0]
        products = zone_products(temp_class)
        while True:
            desc = f"{rng.choice(products)} {rng.choice(PACK_SIZES)}"
            if desc not in used_descriptions:
                used_descriptions.add(desc)
                break
        items.append(
            {
                "sku": f"SKU-{i:05d}",
                "description": desc,
                "velocity_class": velocity,
                "temperature_class": temp_class,
                "uom": rng.choice(["EA", "CS"]),
                "case_pack": rng.choice([1, 6, 12, 24, 48]),
            }
        )
    return items


def generate_inventory(
    rng: random.Random,
    items: list[dict],
    locations_by_temp: dict[str, list[str]],
    reference_date: date,
) -> tuple[list[dict], dict[str, list[str]]]:
    """Returns (inventory_rows, sku -> [location_code, ...] actually holding it)."""
    inventory = []
    sku_locations: dict[str, list[str]] = {}
    for item in items:
        temp_class = item["temperature_class"]
        candidate_locations = locations_by_temp[temp_class]
        num_lots = rng.randint(1, 4)
        chosen_locations = rng.sample(
            candidate_locations, k=min(num_lots, len(candidate_locations))
        )
        sku_locations[item["sku"]] = chosen_locations
        for loc_code in chosen_locations:
            days_ago = rng.randint(1, 60)
            receipt_date = reference_date - timedelta(days=days_ago)
            expiry = None
            # A small share of ambient items are non-perishable (no expiry
            # tracking) — realistic for canned/dry goods vs. fresh product.
            if not (temp_class == "ambient" and rng.random() < 0.15):
                expiry = receipt_date + timedelta(days=shelf_life_days(temp_class, rng))
            inventory.append(
                {
                    "location_code": loc_code,
                    "sku": item["sku"],
                    "quantity": rng.randint(1, 10) * item["case_pack"],
                    "lot_number": f"LOT{receipt_date.strftime('%y%m%d')}-{rng.randint(1, 999):03d}",
                    "expiry_date": expiry,
                    "receipt_date": receipt_date,
                }
            )
    return inventory, sku_locations


def generate_picks(
    rng: random.Random,
    items: list[dict],
    sku_locations: dict[str, list[str]],
    employee_ids: list[str],
    reference_date: date,
    lookback_days: int,
    count: int,
) -> list[dict]:
    picks = []
    skus = [i["sku"] for i in items]
    weights = [VELOCITY_PICK_WEIGHT[i["velocity_class"]] for i in items]
    order_id = 1
    picks_left_in_order = 0
    current_order = None

    for _ in range(count):
        if picks_left_in_order <= 0:
            current_order = f"ORD-{order_id:06d}"
            order_id += 1
            picks_left_in_order = rng.randint(1, 6)
        picks_left_in_order -= 1

        sku = rng.choices(skus, weights=weights)[0]
        loc_codes = sku_locations.get(sku)
        if not loc_codes:
            continue
        days_ago = rng.randint(0, lookback_days)
        pick_date = reference_date - timedelta(days=days_ago)
        # Warehouse shift hours, weighted toward business hours, not 24h uniform.
        hour = rng.choices(range(24), weights=[1] * 6 + [4] * 12 + [1] * 6)[0]
        ts = datetime.combine(pick_date, time(hour=hour, minute=rng.randint(0, 59)))

        picks.append(
            {
                "sku": sku,
                "quantity": rng.randint(1, 5),
                "location_code": rng.choice(loc_codes),
                "picker_id": rng.choice(employee_ids),
                "ts": ts,
                "order_id": current_order,
            }
        )
    return picks


def generate_receipts(
    rng: random.Random, reference_date: date, lookback_days: int, count: int
) -> list[dict]:
    receipts = []
    for i in range(1, count + 1):
        days_ago = rng.randint(0, lookback_days)
        arrival = datetime.combine(
            reference_date - timedelta(days=days_ago),
            time(hour=rng.randint(5, 20), minute=rng.randint(0, 59)),
        )
        # Realistic dock-to-stock spread: a fast majority, a slow tail.
        bucket = rng.random()
        if bucket < 0.70:
            dock_to_stock_minutes = rng.randint(30, 90)
        elif bucket < 0.90:
            dock_to_stock_minutes = rng.randint(90, 240)
        else:
            dock_to_stock_minutes = rng.randint(240, 720)
        # A small share are still mid-putaway (no completion time yet).
        complete = None if rng.random() < 0.03 else arrival + timedelta(minutes=dock_to_stock_minutes)
        receipts.append(
            {
                "carrier": rng.choice(CARRIERS),
                "po_number": f"PO-{100000 + i}",
                "arrival_time": arrival,
                "put_away_complete_time": complete,
                "pallet_count": rng.choice([1, 2, 4, 8, 12, 16, 20, 26, 30]),
            }
        )
    return receipts


def generate_labor(
    rng: random.Random, employee_ids: list[str], reference_date: date, lookback_days: int
) -> list[dict]:
    labor = []
    # Each employee is primarily assigned to one zone (occasional float).
    home_zone = {emp: rng.choice(["FRZ", "CHL", "AMB"]) for emp in employee_ids}
    zone_pph_baseline = {"FRZ": 65, "CHL": 85, "AMB": 100}  # PPE/cold slows frozen picking
    zone_dts_baseline = {"FRZ": 95, "CHL": 70, "AMB": 55}

    for day_offset in range(lookback_days):
        shift_date = reference_date - timedelta(days=day_offset)
        for emp in employee_ids:
            # ~5-day work week, not every employee every day.
            if rng.random() < 2 / 7:
                continue
            zone = home_zone[emp] if rng.random() < 0.85 else rng.choice(["FRZ", "CHL", "AMB"])
            pph = max(20.0, rng.gauss(zone_pph_baseline[zone], 12))
            dts = max(15.0, rng.gauss(zone_dts_baseline[zone], 20))
            labor.append(
                {
                    "employee_id": emp,
                    "shift_date": shift_date,
                    "zone": zone,
                    "picks_per_hour": round(pph, 1),
                    "dock_to_stock_minutes": round(dts, 1),
                }
            )
    return labor


def _chunked(rows: list[dict], size: int = 1000):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _bulk_insert(conn, table, rows: list[dict]) -> None:
    """Inserts via a Core `Insert()` construct, not raw `text()` SQL.

    This distinction matters a lot over a high-latency connection (e.g.
    seeding a remote Railway DB through its public proxy instead of
    locally): SQLAlchemy 2.0's `insertmanyvalues` batching — which packs
    many rows into one multi-row `INSERT ... VALUES (...), (...), ...`
    statement — only activates for `Insert()` constructs. The same call
    written as `conn.execute(text("INSERT ..."), rows)` silently falls
    back to psycopg2's `executemany()`, which issues one network round
    trip PER ROW. That difference is why an earlier version of this
    script took 15+ minutes and then died mid-transaction (connection
    dropped under a long-held transaction) seeding 20k picks through a
    public proxy, versus a couple of seconds against a local/low-latency
    Postgres — the row count didn't change, the round-trip count did.
    """
    if not rows:
        return
    for chunk in _chunked(rows):
        conn.execute(insert(table), chunk)


def load_into_db(
    locations, items, inventory, picks, receipts, labor, echo: bool = True
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE inventory, picks, receipts, labor, items, locations "
                "RESTART IDENTITY CASCADE"
            )
        )

        _bulk_insert(conn, Location.__table__, locations)
        _bulk_insert(conn, Item.__table__, items)

        # inventory/picks reference locations by location_id, not code — resolve via a
        # lookup built from what we just inserted, so we don't have to guess IDs.
        loc_id_by_code = dict(conn.execute(text("SELECT location_code, id FROM locations")).all())

        _bulk_insert(
            conn,
            Inventory.__table__,
            [
                {**row, "location_id": loc_id_by_code[row.pop("location_code")]}
                for row in inventory
            ],
        )
        _bulk_insert(
            conn,
            Pick.__table__,
            [{**row, "location_id": loc_id_by_code[row.pop("location_code")]} for row in picks],
        )
        _bulk_insert(conn, Receipt.__table__, receipts)
        _bulk_insert(conn, Labor.__table__, labor)

    if echo:
        print(
            f"Loaded: {len(locations)} locations, {len(items)} items, "
            f"{len(inventory)} inventory rows, {len(picks)} picks, "
            f"{len(receipts)} receipts, {len(labor)} labor rows."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--locations", type=int, default=80)
    parser.add_argument("--items", type=int, default=250)
    parser.add_argument("--picks", type=int, default=20000)
    parser.add_argument("--receipts", type=int, default=500)
    parser.add_argument("--employees", type=int, default=30)
    parser.add_argument("--lookback-days", type=int, default=90)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    Faker.seed(args.seed)

    reference_date = date.today()

    locations = generate_locations(rng, args.locations)
    items = generate_items(rng, args.items)

    locations_by_temp: dict[str, list[str]] = {"frozen": [], "chilled": [], "ambient": []}
    for loc in locations:
        locations_by_temp[loc["temperature_zone"]].append(loc["location_code"])

    inventory, sku_locations = generate_inventory(rng, items, locations_by_temp, reference_date)

    employee_ids = [f"EMP-{i:03d}" for i in range(1, args.employees + 1)]

    picks = generate_picks(
        rng, items, sku_locations, employee_ids, reference_date, args.lookback_days, args.picks
    )
    receipts = generate_receipts(rng, reference_date, args.lookback_days, args.receipts)
    labor = generate_labor(rng, employee_ids, reference_date, args.lookback_days)

    load_into_db(locations, items, inventory, picks, receipts, labor)


if __name__ == "__main__":
    main()
