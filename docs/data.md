# Data

OpsVision keeps everything in one SQLite database. The layout is in [`opsvision/schema.sql`](../opsvision/schema.sql).

## What is stored

Reference lists:

- dates
- suppliers
- materials
- products
- plants
- warehouses
- regions

Activity:

- customer orders
- shipments
- purchase orders
- daily inventory snapshots
- production runs
- defects
- returns
- demand forecasts

`mart_order_fulfillment` is a view with one row per order line. It already flags whether the line was on time, in full, both, short, and how many days it took. Most of the service measures read from this view. The same questions are written out as queries in [`sql/analysis.sql`](../sql/analysis.sql).

## Load your own files

Export one CSV per table, using the table names and column headers that `export` writes. Then load them into a new database:

```bash
python3 -m opsvision ingest --input-dir /path/to/csvs --db data/operations.db
python3 -m opsvision serve --db data/operations.db
python3 -m opsvision report --db data/operations.db
```

The loader checks headers and relationships between tables. If the import fails, it removes the unfinished database. Map source-system fields, and assign one failure reason per late or short order line, before you load.

`python3 -m opsvision export` writes every table, plus the order-line view, as CSV. Those files open in Excel, Power BI, or Tableau.

## What one row means

| File | One row represents | Key point |
| --- | --- | --- |
| fact_orders.csv | One product line on a customer order | One order_id per row |
| fact_shipments.csv | The completed shipment for one order line | One shipment per order_id in this version |
| fact_purchase_orders.csv | One purchase order for a supplier and material | Receipt date is used for lead-time reporting |
| fact_inventory_snapshot.csv | One product in one warehouse on one day | Date, product, and warehouse are unique together |
| fact_production_runs.csv | One production run | Good, scrap, downtime, and cost come from this row |
| fact_defects.csv | One defect type recorded on a run | Several defect rows can belong to one run |
| fact_returns.csv | One return against an order line | Several returns can belong to one order |
| fact_forecast.csv | One product and warehouse forecast on one day | Includes both forecast and actual demand |

The dimension files hold names and categories. An ID used in a fact file must exist in the matching dimension file. Dates used as order dates, stock dates, run dates, and forecast dates must exist in dim_date.csv.

## Prepare an extract

1. Build the sample database and run export once. Use the exported headers as templates.
2. Give every order line a stable, unique order_id. If a source order contains several products, make one row per product line.
3. Bring multiple deliveries against one order line together before loading. The current shipment table expects one completed shipment record per order line.
4. Write dates as YYYY-MM-DD. Keep quantities and costs nonnegative and use one unit of measure for each product.
5. For every failed order, choose one main reason from Supplier delays, Production downtime, Inventory shortages, Transportation delays, or Other. Leave the reason empty for an order that arrived on time and in full.
6. Put the full set of CSVs in one folder and load into a new database path.
7. Open the dashboard and compare counts and a few source orders with the original extracts.

The loader checks that CSV headers match the schema and that linked IDs exist. It does not decide which source field means a promised date, combine partial shipments, or judge the main reason for a late order. Those mapping decisions belong in the extract preparation step.

## If a load fails

The error will name a missing file, a mismatched set of columns, or a database relationship that did not pass. Fix the CSVs and choose a new output database path. The loader will not overwrite an existing database.
