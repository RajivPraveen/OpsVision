"""Deterministic, clearly synthetic operational data for the demo."""

import argparse
import datetime as dt
import random
import sqlite3
from pathlib import Path

DEFAULT_DB = Path.cwd() / "data" / "opsvision.db"
REASONS = ["Supplier delays", "Production downtime", "Inventory shortages",
           "Transportation delays", "Other"]


def iso(day):
    return day.isoformat()


def seed_database(path=DEFAULT_DB, as_of=None):
    """Rebuild a portable SQLite demo with a deliberate, explainable OTIF decline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    rng = random.Random(42)
    today = as_of or dt.date.today()
    # Keep a full settlement buffer for late shipments and returns.
    end = today - dt.timedelta(days=(today.weekday() + 1) % 7 + 7)
    history_days = 196  # enough for two complete 90-day comparison periods
    current_start = history_days - 28
    previous_start = history_days - 56
    spike_start = history_days - 14
    start = end - dt.timedelta(days=history_days - 1)
    days = [start + dt.timedelta(days=i) for i in range(history_days)]
    con = sqlite3.connect(str(path))
    con.executescript((Path(__file__).with_name("schema.sql")).read_text())

    materials = [("M01", "Copper", "Metal"), ("M02", "Resin", "Polymer"),
                 ("M03", "Silicon", "Semiconductor"), ("M04", "Aluminum", "Metal")]
    suppliers = [("S042", "Apex Components", "Asia Pacific", "High"),
                 ("S017", "Delta Materials", "North America", "Medium"),
                 ("S026", "Northstar Electronics", "Europe", "Low"),
                 ("S031", "Meridian Industrial", "Asia Pacific", "Medium"),
                 ("S055", "Summit Supply", "North America", "Low")]
    products = [
        ("PR01", "CTRL-100", "Control Module", "Electronics", "M03", 82.0),
        ("PR02", "SENS-220", "Sensor Array", "Electronics", "M03", 56.0),
        ("PR03", "CABL-340", "Cable Assembly", "Electrical", "M01", 24.0),
        ("PR04", "HOUS-410", "Enclosure", "Mechanical", "M04", 38.0),
        ("PR05", "CONN-520", "Connector Set", "Electrical", "M01", 18.0),
        ("PR06", "ACTR-630", "Actuator", "Mechanical", "M04", 74.0),
        ("PR07", "SEAL-710", "Seal Kit", "Mechanical", "M02", 12.0),
        ("PR08", "PWR-840", "Power Board", "Electronics", "M03", 96.0),
        ("PR09", "TRAY-910", "Packaging Tray", "Packaging", "M02", 8.0),
        ("PR10", "BRKT-115", "Mounting Bracket", "Mechanical", "M04", 15.0),
        ("PR11", "WIRE-125", "Wire Harness", "Electrical", "M01", 31.0),
        ("PR12", "CHIP-135", "Logic Chip", "Electronics", "M03", 108.0),
    ]
    plants = [("P01", "Austin Plant", "North America"),
              ("P02", "Monterrey Plant", "North America"),
              ("P03", "Penang Plant", "Asia Pacific")]
    warehouses = [("W01", "Dallas DC", "North America"),
                  ("W02", "Rotterdam DC", "Europe")]
    geographies = [("G01", "United States", "US"),
                   ("G02", "Germany", "DE"), ("G03", "Mexico", "MX"),
                   ("G04", "Singapore", "SG")]
    con.executemany("INSERT INTO dim_material VALUES (?,?,?)", materials)
    con.executemany("INSERT INTO dim_supplier VALUES (?,?,?,?)", suppliers)
    con.executemany("INSERT INTO dim_product VALUES (?,?,?,?,?,?)", products)
    con.executemany("INSERT INTO dim_plant VALUES (?,?,?)", plants)
    con.executemany("INSERT INTO dim_warehouse VALUES (?,?,?)", warehouses)
    con.executemany("INSERT INTO dim_geography VALUES (?,?,?)", geographies)
    con.executemany("INSERT INTO dim_date VALUES (?,?,?,?)", [
        (iso(d), iso(d - dt.timedelta(days=d.weekday())), d.strftime("%Y-%m"),
         "%s-Q%s" % (d.year, (d.month - 1) // 3 + 1)) for d in days
    ])

    # 25 lines/day gives 700 lines in each comparison window. The two windows
    # contain 42 and 98 failures (94% and 86% OTIF). Cause counts are generated
    # at the order grain, then attributed exactly by SQL in analytics.py.
    orders = []
    for day_idx, day in enumerate(days):
        for _ in range(25):
            product = rng.choice(products)
            supplier = rng.choices([x[0] for x in suppliers], [27, 25, 17, 17, 14])[0]
            plant = rng.choices([x[0] for x in plants], [35, 40, 25])[0]
            warehouse = rng.choice(warehouses)[0]
            geo = rng.choices([x[0] for x in geographies], [40, 25, 20, 15])[0]
            qty = rng.randint(12, 130)
            orders.append((len(orders) + 1, day_idx, day, product[0], supplier,
                           plant, warehouse, geo, qty, round(product[5] * 1.42, 2)))

    failures = {}
    def assign_window(first, last, counts):
        remaining = list(range(first * 25, last * 25))
        for reason, count in zip(REASONS, counts):
            def weight(index):
                o = orders[index]
                factor = 1.0
                if reason == "Supplier delays" and o[4] in ("S042", "S017"):
                    factor = 6.0 if o[4] == "S042" else 2.2
                elif reason == "Production downtime" and o[5] == "P02":
                    factor = 5.5
                elif reason == "Inventory shortages" and o[3] in ("PR02", "PR12"):
                    factor = 5.0
                elif reason == "Transportation delays" and o[7] in ("G02", "G04"):
                    factor = 4.5
                return rng.random() ** (1.0 / factor)
            chosen = sorted(remaining, key=weight, reverse=True)[:count]
            for index in chosen:
                failures[index] = reason
            selected = set(chosen)
            remaining = [x for x in remaining if x not in selected]

    for block in range(5):
        assign_window(block * 28, (block + 1) * 28, [14, 11, 9, 9, 11])
    assign_window(previous_start, current_start, [10, 9, 7, 7, 9])
    assign_window(current_start, history_days, [32, 27, 17, 13, 9])

    order_rows, shipment_rows, return_rows = [], [], []
    for index, o in enumerate(orders):
        order_id, _, day, product, supplier, plant, warehouse, geo, qty, price = o
        promised = day + dt.timedelta(days=3)
        reason = failures.get(index)
        late = reason in ("Supplier delays", "Production downtime", "Transportation delays", "Other")
        short = reason in ("Inventory shortages", "Other")
        delay_days = rng.randint(1, 3) if late else -rng.randint(0, 1)
        if reason == "Transportation delays" and o[1] >= spike_start:
            delay_days += 3
        delivery = promised + dt.timedelta(days=delay_days)
        delivered = qty - rng.randint(1, max(2, qty // 4)) if short else qty
        ship = delivery - dt.timedelta(days=1)
        order_rows.append((order_id, iso(day), iso(promised), product, supplier,
                           plant, warehouse, geo, qty, price))
        shipment_rows.append((order_id, order_id, iso(ship), iso(delivery), delivered,
                              round(qty * rng.uniform(0.6, 1.5), 2), reason))
        if rng.random() < (0.036 if not reason else 0.09):
            return_rows.append((len(return_rows) + 1, order_id,
                                iso(delivery + dt.timedelta(days=rng.randint(1, 7))),
                                rng.randint(1, max(2, delivered // 6)),
                                rng.choice(["Quality", "Damage", "Incorrect item"])))
    con.executemany("INSERT INTO fact_orders VALUES (?,?,?,?,?,?,?,?,?,?)", order_rows)
    con.executemany("INSERT INTO fact_shipments VALUES (?,?,?,?,?,?,?)", shipment_rows)
    con.executemany("INSERT INTO fact_returns VALUES (?,?,?,?,?)", return_rows)

    po_rows = []
    for day_idx, day in enumerate(days):
        for supplier in suppliers:
            if rng.random() > 0.75:
                continue
            supplier_id = supplier[0]
            material = rng.choice(materials)[0]
            baseline = 8 + rng.choice([-2, -1, 0, 0, 1, 2])
            lead = (19 + rng.choice([-1, 0, 1])) if supplier_id == "S042" and day_idx >= spike_start - 19 else baseline
            expected = day + dt.timedelta(days=9)
            received = day + dt.timedelta(days=lead)
            if received > end:
                continue
            qty = rng.randint(250, 1100)
            po_rows.append((len(po_rows) + 1, iso(day), supplier_id, material,
                            rng.choice(plants)[0], iso(expected), iso(received),
                            qty, qty - (rng.randint(10, 70) if lead > 13 else 0),
                            round(rng.uniform(4.5, 18.5), 2)))
    con.executemany("INSERT INTO fact_purchase_orders VALUES (?,?,?,?,?,?,?,?,?,?)", po_rows)

    inventory_rows, forecast_rows = [], []
    stock = {(p[0], w[0]): rng.randint(170, 330) for p in products for w in warehouses}
    for day_idx, day in enumerate(days):
        for product in products:
            for warehouse in warehouses:
                key = (product[0], warehouse[0])
                actual = rng.randint(14, 38)
                forecast = max(1, actual + rng.randint(-8, 8) + (12 if day_idx >= current_start and product[0] in ("PR02", "PR12") else 0))
                replenish = rng.randint(225, 310) if day_idx % 9 == (int(product[0][-2:]) % 9) else 0
                stock[key] = max(0, stock[key] + replenish - actual)
                if day_idx >= spike_start - 4 and product[0] in ("PR02", "PR12") and warehouse[0] == "W01":
                    stock[key] = max(0, stock[key] - rng.randint(38, 52))
                if day_idx == history_days - 9 and product[0] == "PR12" and warehouse[0] == "W01":
                    stock[key] = 0
                on_hand = stock[key]
                allocated = min(on_hand, rng.randint(5, 30))
                inventory_rows.append((iso(day), warehouse[0], product[0], on_hand,
                                       allocated, actual, round(on_hand * product[5], 2),
                                       int(on_hand < actual)))
                forecast_rows.append((iso(day), product[0], warehouse[0], forecast, actual))
    con.executemany("INSERT INTO fact_inventory_snapshot VALUES (?,?,?,?,?,?,?,?)", inventory_rows)
    con.executemany("INSERT INTO fact_forecast VALUES (?,?,?,?,?)", forecast_rows)

    run_rows, defect_rows = [], []
    for day_idx, day in enumerate(days):
        for plant in plants:
            for _ in range(2):
                product = rng.choice(products)
                planned = rng.randint(180, 430)
                downtime = max(0, round(rng.gauss(22, 8)))
                if day_idx >= current_start and plant[0] == "P02":
                    downtime += rng.randint(45, 75) + (70 if day_idx >= spike_start else 0)
                scrap_rate = 0.018 + (0.028 if day_idx >= current_start and plant[0] == "P02" else 0)
                scrap = max(0, round(planned * scrap_rate + rng.gauss(0, 2)))
                good = max(0, planned - scrap - round(downtime * 0.18))
                defect_qty = max(0, round(good * (0.017 + (0.035 if day_idx >= current_start and plant[0] == "P02" else 0)
                                                   + (0.045 if day_idx >= spike_start and plant[0] == "P02" else 0))
                                            + rng.gauss(0, 2)))
                run_id = len(run_rows) + 1
                run_rows.append((run_id, iso(day), plant[0], product[0], planned,
                                 good, scrap, downtime, 480,
                                 round(planned * product[5] * rng.uniform(1.03, 1.11), 2)))
                if defect_qty:
                    defect_rows.append((len(defect_rows) + 1, run_id,
                                        rng.choice(["Electrical test", "Dimensional", "Cosmetic"]), defect_qty))
    con.executemany("INSERT INTO fact_production_runs VALUES (?,?,?,?,?,?,?,?,?,?)", run_rows)
    con.executemany("INSERT INTO fact_defects VALUES (?,?,?,?)", defect_rows)
    con.commit()
    con.close()
    return {"database": str(path), "start": iso(start), "end": iso(end),
            "orders": len(order_rows), "purchase_orders": len(po_rows),
            "inventory_snapshots": len(inventory_rows)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build OpsVision demo data")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", type=dt.date.fromisoformat)
    args = parser.parse_args()
    print(seed_database(args.db, args.as_of))
