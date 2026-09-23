PRAGMA foreign_keys = ON;

CREATE TABLE dim_material (
  material_id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL
);
CREATE TABLE dim_supplier (
  supplier_id TEXT PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL,
  risk_tier TEXT NOT NULL
);
CREATE TABLE dim_product (
  product_id TEXT PRIMARY KEY, sku TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  category TEXT NOT NULL, material_id TEXT NOT NULL REFERENCES dim_material(material_id),
  standard_cost REAL NOT NULL
);
CREATE TABLE dim_plant (
  plant_id TEXT PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL
);
CREATE TABLE dim_warehouse (
  warehouse_id TEXT PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL
);
CREATE TABLE dim_geography (
  geography_id TEXT PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL
);
CREATE TABLE dim_date (
  date_key TEXT PRIMARY KEY, week_start TEXT NOT NULL, month_key TEXT NOT NULL,
  quarter_key TEXT NOT NULL
);

CREATE TABLE fact_orders (
  order_id INTEGER PRIMARY KEY, order_date TEXT NOT NULL REFERENCES dim_date(date_key),
  promised_date TEXT NOT NULL, product_id TEXT NOT NULL REFERENCES dim_product(product_id),
  supplier_id TEXT NOT NULL REFERENCES dim_supplier(supplier_id),
  plant_id TEXT NOT NULL REFERENCES dim_plant(plant_id),
  warehouse_id TEXT NOT NULL REFERENCES dim_warehouse(warehouse_id),
  geography_id TEXT NOT NULL REFERENCES dim_geography(geography_id),
  ordered_qty INTEGER NOT NULL, unit_price REAL NOT NULL
);
CREATE TABLE fact_shipments (
  shipment_id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL UNIQUE REFERENCES fact_orders(order_id),
  ship_date TEXT NOT NULL, delivery_date TEXT NOT NULL, delivered_qty INTEGER NOT NULL,
  freight_cost REAL NOT NULL, primary_failure_reason TEXT,
  CHECK(primary_failure_reason IN ('Supplier delays','Production downtime',
    'Inventory shortages','Transportation delays','Other') OR primary_failure_reason IS NULL)
);
CREATE TABLE fact_purchase_orders (
  po_id INTEGER PRIMARY KEY, order_date TEXT NOT NULL REFERENCES dim_date(date_key),
  supplier_id TEXT NOT NULL REFERENCES dim_supplier(supplier_id),
  material_id TEXT NOT NULL REFERENCES dim_material(material_id),
  plant_id TEXT NOT NULL REFERENCES dim_plant(plant_id),
  expected_date TEXT NOT NULL, received_date TEXT NOT NULL,
  ordered_qty INTEGER NOT NULL, received_qty INTEGER NOT NULL, unit_cost REAL NOT NULL
);
CREATE TABLE fact_inventory_snapshot (
  date_key TEXT NOT NULL REFERENCES dim_date(date_key),
  warehouse_id TEXT NOT NULL REFERENCES dim_warehouse(warehouse_id),
  product_id TEXT NOT NULL REFERENCES dim_product(product_id),
  on_hand_qty INTEGER NOT NULL, allocated_qty INTEGER NOT NULL,
  units_sold INTEGER NOT NULL, inventory_value REAL NOT NULL,
  stockout_flag INTEGER NOT NULL CHECK(stockout_flag IN (0,1)),
  PRIMARY KEY (date_key, warehouse_id, product_id)
);
CREATE TABLE fact_production_runs (
  run_id INTEGER PRIMARY KEY, date_key TEXT NOT NULL REFERENCES dim_date(date_key),
  plant_id TEXT NOT NULL REFERENCES dim_plant(plant_id),
  product_id TEXT NOT NULL REFERENCES dim_product(product_id),
  planned_units INTEGER NOT NULL, good_units INTEGER NOT NULL,
  scrap_units INTEGER NOT NULL, downtime_minutes INTEGER NOT NULL,
  planned_minutes INTEGER NOT NULL, total_cost REAL NOT NULL
);
CREATE TABLE fact_defects (
  defect_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES fact_production_runs(run_id),
  defect_type TEXT NOT NULL, defect_qty INTEGER NOT NULL
);
CREATE TABLE fact_returns (
  return_id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES fact_orders(order_id),
  return_date TEXT NOT NULL, returned_qty INTEGER NOT NULL, reason TEXT NOT NULL
);
CREATE TABLE fact_forecast (
  date_key TEXT NOT NULL REFERENCES dim_date(date_key),
  product_id TEXT NOT NULL REFERENCES dim_product(product_id),
  warehouse_id TEXT NOT NULL REFERENCES dim_warehouse(warehouse_id),
  forecast_qty INTEGER NOT NULL, actual_demand INTEGER NOT NULL,
  PRIMARY KEY (date_key, product_id, warehouse_id)
);

CREATE INDEX ix_orders_date ON fact_orders(order_date);
CREATE INDEX ix_orders_dims ON fact_orders(supplier_id, plant_id, geography_id, product_id);
CREATE INDEX ix_shipments_delivery ON fact_shipments(delivery_date);
CREATE INDEX ix_inventory_date ON fact_inventory_snapshot(date_key);
CREATE INDEX ix_production_date ON fact_production_runs(date_key);
CREATE INDEX ix_po_date ON fact_purchase_orders(order_date);

-- Order level KPI mart. The exclusive primary_failure_reason makes the
-- period-over-period OTIF bridge mathematically additive.
CREATE VIEW mart_order_fulfillment AS
SELECT o.*, s.delivery_date, s.ship_date, s.delivered_qty, s.freight_cost,
       s.primary_failure_reason,
       CASE WHEN s.delivery_date <= o.promised_date THEN 1 ELSE 0 END AS on_time,
       CASE WHEN s.delivered_qty >= o.ordered_qty THEN 1 ELSE 0 END AS in_full,
       CASE WHEN s.delivery_date <= o.promised_date AND s.delivered_qty >= o.ordered_qty
            THEN 1 ELSE 0 END AS otif,
       CASE WHEN s.delivered_qty < o.ordered_qty THEN 1 ELSE 0 END AS backordered,
       CAST(julianday(s.delivery_date) - julianday(o.order_date) AS INTEGER) AS cycle_days
FROM fact_orders o JOIN fact_shipments s ON s.order_id = o.order_id;
