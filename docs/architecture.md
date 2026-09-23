# How OpsVision is built

OpsVision runs as a small local web application. Python serves the page and calculates the numbers; SQLite stores the records; HTML, CSS, and JavaScript draw the dashboard. No JavaScript build step or paid service is needed.

## From a record to a screen

1. **Load data.** The sample-data builder creates a repeatable database. For other data, the CSV loader reads one file per table, checks its columns, and checks that linked records exist.
2. **Store the activity.** Orders, shipments, purchasing, stock, production, defects, returns, and forecasts each have their own table. Supplier, product, material, plant, warehouse, geography, and date tables hold the names used across those records.
3. **Calculate measures.** The analytics module queries the stored activity. It calculates delivery and stock rates, breaks down the delivery change, finds unusual readings, and estimates demand.
4. **Show the result.** The server exposes the results as JSON. The dashboard uses that JSON for cards, charts, tables, and filters. The report generator uses the same calculations to produce HTML and Markdown.

## Why the tables are separate

One order can have a shipment and may later have a return. A production run may have several defect records. A stock count belongs to a product, a warehouse, and a date. Keeping these as separate records avoids accidentally counting an order several times when the data is joined.

The main delivery view, **mart_order_fulfillment**, combines each order line with its one shipment. It flags whether the order was on time, filled in full, both, or delivered short. It also measures the days from order to delivery. Each row still represents one order line.

## What filters change

The supplier, plant, geography, product, and material filters affect order-based measures. Other measures use only dimensions present in their records:

| Source | Filters that apply |
| --- | --- |
| Orders and shipments | supplier, plant, geography, product, material, warehouse |
| Purchase orders | supplier, plant, material |
| Stock snapshots and forecasts | product, material, warehouse |
| Production runs and defects | plant, product, material |

For example, stock snapshots do not name a supplier. Filtering to one supplier therefore does not silently assign that supplier a share of warehouse stock. Inventory turnover uses delivered-unit cost and inventory value with the same product, material, and warehouse scope.

## Delivery change

Every late or short order has one recorded main reason. For each reason, the app compares its share of all order lines in the current period with its share in the prior period. When all reasons are added together, the result equals the change in on-time, in-full delivery before rounding.

This is a breakdown of the **recorded reasons**. It cannot, by itself, prove what would have happened if a supplier or process had been different.

## Alerts and forecast

Alerts compare the latest 14 days with the 90 days before them. Lead time, defect rate, and downtime use recent average readings; stock and shipping also check sudden individual events. Alerts require enough observations in both windows.

The two-week demand estimate looks at the latest four weeks by weekday and adjusts for a capped change from the four weeks before that. It is intentionally simple and can be inspected or replaced without changing the page.

## Code map

| File | Purpose |
| --- | --- |
| [schema.sql](../opsvision/schema.sql) | Database tables and delivery view |
| [seed.py](../opsvision/seed.py) | Sample records |
| [ingest.py](../opsvision/ingest.py) | CSV import |
| [analytics.py](../opsvision/analytics.py) | Measures, delivery breakdown, alerts, and forecast |
| [server.py](../opsvision/server.py) | Web page and JSON endpoints |
| [report.py](../opsvision/report.py) | Weekly report |
| [web/](../opsvision/web/) | Dashboard page, styles, and browser code |

