"""CSV extracts for Excel, Power BI, Tableau and ad hoc SQL validation."""

import csv
from pathlib import Path

from .analytics import connect
from .seed import DEFAULT_DB

TABLES = ["dim_date", "dim_material", "dim_supplier", "dim_product", "dim_plant",
          "dim_warehouse", "dim_geography", "fact_orders", "fact_shipments",
          "fact_purchase_orders", "fact_inventory_snapshot", "fact_production_runs",
          "fact_defects", "fact_returns", "fact_forecast", "mart_order_fulfillment"]


def export_csv(db=DEFAULT_DB, output_dir=Path("exports")):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    con = connect(db)
    paths = []
    try:
        for table in TABLES:
            cursor = con.execute("SELECT * FROM " + table)
            path = output_dir / (table + ".csv")
            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow([column[0] for column in cursor.description])
                writer.writerows(cursor)
            paths.append(path)
    finally:
        con.close()
    return paths
