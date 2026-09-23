-- Example queries for OpsVision. Run them against data/opsvision.db.

-- 1. Weekly OTIF and perfect-order performance by supplier.
SELECT d.week_start, s.supplier_id, s.name AS supplier,
       COUNT(*) AS order_lines,
       ROUND(100.0 * SUM(f.otif) / COUNT(*), 1) AS otif_pct,
       ROUND(100.0 * SUM(CASE WHEN f.otif = 1 AND NOT EXISTS
         (SELECT 1 FROM fact_returns r WHERE r.order_id = f.order_id)
         THEN 1 ELSE 0 END) / COUNT(*), 1) AS perfect_order_pct
FROM mart_order_fulfillment f
JOIN dim_date d ON d.date_key = f.order_date
JOIN dim_supplier s ON s.supplier_id = f.supplier_id
GROUP BY d.week_start, s.supplier_id, s.name
ORDER BY d.week_start, otif_pct;

-- 2. Exact 28-day OTIF attribution. The sum of change_pp equals the OTIF delta.
WITH latest AS (SELECT MAX(order_date) AS end_date FROM fact_orders),
periodized AS (
  SELECT CASE WHEN julianday(l.end_date)-julianday(f.order_date) < 28
              THEN 'current' ELSE 'previous' END AS period,
         COALESCE(f.primary_failure_reason, 'On time in full') AS reason
  FROM mart_order_fulfillment f CROSS JOIN latest l
  WHERE julianday(l.end_date)-julianday(f.order_date) BETWEEN 0 AND 55
), counts AS (
  SELECT period, reason, COUNT(*) AS n FROM periodized GROUP BY period, reason
), totals AS (
  SELECT period, COUNT(*) AS n FROM periodized GROUP BY period
)
SELECT c.reason, c.n AS current_misses, p.n AS previous_misses,
       ROUND(100.0 * p.n / pt.n - 100.0 * c.n / ct.n, 2) AS change_pp
FROM counts c JOIN counts p ON p.reason=c.reason AND p.period='previous'
JOIN totals ct ON ct.period='current' JOIN totals pt ON pt.period='previous'
WHERE c.period='current' AND c.reason<>'On time in full'
ORDER BY change_pp;

-- 3. Supplier lead-time variation (recent vs preceding 90 days).
WITH latest AS (SELECT MAX(received_date) AS end_date FROM fact_purchase_orders),
samples AS (
  SELECT supplier_id,
         CASE WHEN julianday(l.end_date)-julianday(po.received_date)<14
              THEN 'recent' ELSE 'baseline' END AS period,
         julianday(received_date)-julianday(po.order_date) AS lead_days
  FROM fact_purchase_orders po CROSS JOIN latest l
  WHERE julianday(l.end_date)-julianday(po.received_date) BETWEEN 0 AND 103
)
SELECT s.name, x.period, COUNT(*) AS purchase_orders,
       ROUND(AVG(x.lead_days),2) AS avg_lead_days,
       ROUND(AVG(x.lead_days*x.lead_days)-AVG(x.lead_days)*AVG(x.lead_days),2)
         AS lead_time_variance
FROM samples x JOIN dim_supplier s ON s.supplier_id=x.supplier_id
GROUP BY s.name,x.period ORDER BY s.name,x.period;

-- 4. Inventory coverage using the latest warehouse/SKU snapshot.
SELECT p.sku, p.name AS product, w.name AS warehouse,
       i.on_hand_qty-i.allocated_qty AS available_units,
       ROUND(1.0*(i.on_hand_qty-i.allocated_qty)/NULLIF(i.units_sold,0),1)
         AS available_days_cover
FROM fact_inventory_snapshot i
JOIN dim_product p ON p.product_id=i.product_id
JOIN dim_warehouse w ON w.warehouse_id=i.warehouse_id
WHERE i.date_key=(SELECT MAX(date_key) FROM fact_inventory_snapshot)
ORDER BY available_days_cover ASC;
