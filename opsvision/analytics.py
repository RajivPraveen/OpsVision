"""SQL-backed KPI, attribution, anomaly and forecast calculations."""

import datetime as dt
import math
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

from .seed import DEFAULT_DB, REASONS


DIMENSIONS = {
    "supplier": ("f.supplier_id", "dim_supplier", "supplier_id"),
    "plant": ("f.plant_id", "dim_plant", "plant_id"),
    "geography": ("f.geography_id", "dim_geography", "geography_id"),
    "product": ("f.product_id", "dim_product", "product_id"),
    "material": ("p.material_id", "dim_material", "material_id"),
}


def connect(path=DEFAULT_DB):
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def rows(con, sql, params=()):
    return [dict(row) for row in con.execute(sql, params)]


def one(con, sql, params=()):
    row = con.execute(sql, params).fetchone()
    return dict(row) if row else {}


def safe_div(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def period_bounds(con, days=28, end=None):
    max_date = con.execute("SELECT MAX(order_date) FROM fact_orders").fetchone()[0]
    end_day = dt.date.fromisoformat(end or max_date)
    start = end_day - dt.timedelta(days=days - 1)
    previous_end = start - dt.timedelta(days=1)
    previous_start = previous_end - dt.timedelta(days=days - 1)
    return (start.isoformat(), end_day.isoformat(),
            previous_start.isoformat(), previous_end.isoformat())


def filters_sql(filters, alias="f", include_warehouse=True):
    clauses, args = [], []
    for key in ("supplier", "plant", "geography", "product", "material", "warehouse"):
        value = filters.get(key)
        if not value:
            continue
        if key == "material":
            clauses.append("p.material_id = ?")
        elif key == "warehouse" and include_warehouse:
            clauses.append("%s.warehouse_id = ?" % alias)
        elif key != "warehouse":
            clauses.append("%s.%s_id = ?" % (alias, key))
        else:
            continue
        args.append(value)
    return (" AND " + " AND ".join(clauses)) if clauses else "", args


def order_aggregate(con, start, end, filters):
    clause, params = filters_sql(filters)
    return one(con, """
        SELECT COUNT(*) AS orders, COALESCE(SUM(f.otif),0) AS otif_count,
          COALESCE(SUM(f.on_time),0) AS on_time_count,
          COALESCE(SUM(f.in_full),0) AS in_full_count,
          COALESCE(SUM(f.backordered),0) AS backorders,
          COALESCE(SUM(f.ordered_qty),0) AS ordered_qty,
          COALESCE(SUM(f.delivered_qty),0) AS delivered_qty,
          COALESCE(AVG(f.cycle_days),0) AS cycle_days,
          COALESCE(SUM(CASE WHEN f.otif=1 AND NOT EXISTS
            (SELECT 1 FROM fact_returns r WHERE r.order_id=f.order_id)
            THEN 1 ELSE 0 END),0) AS perfect_orders,
          COALESCE(SUM(f.delivered_qty * p.standard_cost),0) AS cogs
        FROM mart_order_fulfillment f JOIN dim_product p ON p.product_id=f.product_id
        WHERE f.order_date BETWEEN ? AND ?
    """ + clause, [start, end] + params)


def domain_aggregate(con, start, end, filters):
    # Each operational fact is sliced only by dimensions present at its grain.
    inventory_clauses, inventory_args = [], []
    for key, column in (("product", "i.product_id"), ("warehouse", "i.warehouse_id"),
                        ("material", "p.material_id")):
        if filters.get(key):
            inventory_clauses.append(column + "=?")
            inventory_args.append(filters[key])
    where_i = " AND " + " AND ".join(inventory_clauses) if inventory_clauses else ""
    inventory = one(con, """
        SELECT SUM(d.snapshot_count) AS snapshot_count, SUM(d.stockouts) AS stockouts,
          AVG(d.daily_inventory_value) AS avg_inventory_value,
          SUM(d.units_sold) AS units_sold
        FROM (
          SELECT i.date_key, COUNT(*) AS snapshot_count,
            SUM(i.stockout_flag) AS stockouts,
            SUM(i.inventory_value) AS daily_inventory_value,
            SUM(i.units_sold) AS units_sold
          FROM fact_inventory_snapshot i JOIN dim_product p ON p.product_id=i.product_id
          WHERE i.date_key BETWEEN ? AND ?
    """ + where_i + " GROUP BY i.date_key) d", [start, end] + inventory_args)

    prod_clauses, prod_args = [], []
    for key, column in (("plant", "r.plant_id"), ("product", "r.product_id"),
                        ("material", "p.material_id")):
        if filters.get(key):
            prod_clauses.append(column + "=?")
            prod_args.append(filters[key])
    where_p = " AND " + " AND ".join(prod_clauses) if prod_clauses else ""
    production = one(con, """
        SELECT SUM(r.planned_units) AS planned, SUM(r.good_units) AS good,
          SUM(r.scrap_units) AS scrap, SUM(r.downtime_minutes) AS downtime,
          SUM(r.planned_minutes) AS planned_minutes, SUM(r.total_cost) AS total_cost,
          SUM(COALESCE(d.defects,0)) AS defects
        FROM fact_production_runs r JOIN dim_product p ON p.product_id=r.product_id
        LEFT JOIN (SELECT run_id, SUM(defect_qty) AS defects FROM fact_defects GROUP BY run_id) d
          ON d.run_id=r.run_id
        WHERE r.date_key BETWEEN ? AND ?
    """ + where_p, [start, end] + prod_args)

    po_clauses, po_args = [], []
    for key, column in (("supplier", "supplier_id"), ("plant", "plant_id"),
                        ("material", "material_id")):
        if filters.get(key):
            po_clauses.append(column + "=?")
            po_args.append(filters[key])
    where_po = " AND " + " AND ".join(po_clauses) if po_clauses else ""
    purchasing = one(con, """
        SELECT COUNT(*) AS po_count, AVG(julianday(received_date)-julianday(order_date)) AS lead_days,
          SUM(CASE WHEN received_date > expected_date THEN 1 ELSE 0 END) AS late_pos
        FROM fact_purchase_orders WHERE received_date BETWEEN ? AND ?
    """ + where_po, [start, end] + po_args)

    forecast = one(con, """
        SELECT SUM(ABS(x.forecast_qty-x.actual_demand)) AS absolute_error,
          SUM(x.actual_demand) AS actual_demand
        FROM fact_forecast x JOIN dim_product p ON p.product_id=x.product_id
        WHERE x.date_key BETWEEN ? AND ?
    """ + where_i.replace("i.", "x."), [start, end] + inventory_args)
    return inventory, production, purchasing, forecast


def kpis(con, start, end, filters):
    o = order_aggregate(con, start, end, filters)
    i, p, po, fc = domain_aggregate(con, start, end, filters)
    n = o["orders"] or 0
    days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1
    # COGS and inventory value must use the same available dimensions. Supplier,
    # plant and market do not exist on a warehouse snapshot, so omit them here.
    stock_filters = {key: value for key, value in filters.items()
                     if key in ("product", "warehouse", "material")}
    stock_clause, stock_args = filters_sql(stock_filters)
    stock_cogs = one(con, """
        SELECT COALESCE(SUM(f.delivered_qty*p.standard_cost),0) AS cogs
        FROM mart_order_fulfillment f JOIN dim_product p ON p.product_id=f.product_id
        WHERE f.order_date BETWEEN ? AND ?
    """ + stock_clause, [start, end] + stock_args)["cogs"]
    turnover = safe_div(stock_cogs, i["avg_inventory_value"] or 0)
    result = {
        "otif": 100 * safe_div(o["otif_count"], n),
        "inventory_turnover": turnover,
        "days_inventory_outstanding": safe_div(days, turnover),
        "stockout_rate": 100 * safe_div(i["stockouts"] or 0, i["snapshot_count"] or 0),
        "backorder_rate": 100 * safe_div(o["backorders"], n),
        "fill_rate": 100 * safe_div(o["delivered_qty"], o["ordered_qty"]),
        "supplier_lead_time": po["lead_days"] or 0,
        "forecast_accuracy": 100 * max(0, 1 - safe_div(fc["absolute_error"] or 0, fc["actual_demand"] or 0)),
        "defect_rate": 100 * safe_div(p["defects"] or 0, p["good"] or 0),
        "yield": 100 * safe_div(p["good"] or 0, p["planned"] or 0),
        "scrap_rate": 100 * safe_div(p["scrap"] or 0, p["planned"] or 0),
        "production_downtime": 100 * safe_div(p["downtime"] or 0, p["planned_minutes"] or 0),
        "order_cycle_time": o["cycle_days"] or 0,
        "perfect_order_rate": 100 * safe_div(o["perfect_orders"], n),
        "cost_per_unit": safe_div(p["total_cost"] or 0, p["good"] or 0),
    }
    return {key: round(value, 2) for key, value in result.items()}, n


def root_cause(con, start, end, previous_start, previous_end, filters, dimension="supplier"):
    if dimension not in DIMENSIONS:
        raise ValueError("Invalid drilldown dimension")
    clause, args = filters_sql(filters)
    query = """
        SELECT COALESCE(f.primary_failure_reason, 'On time in full') AS reason,
          COUNT(*) AS count
        FROM mart_order_fulfillment f JOIN dim_product p ON p.product_id=f.product_id
        WHERE f.order_date BETWEEN ? AND ?
    """ + clause + " GROUP BY reason"
    current = {r["reason"]: r["count"] for r in rows(con, query, [start, end] + args)}
    previous = {r["reason"]: r["count"] for r in rows(con, query, [previous_start, previous_end] + args)}
    current_n, previous_n = sum(current.values()), sum(previous.values())
    causes = [{"reason": reason, "current_count": current.get(reason, 0),
               "previous_count": previous.get(reason, 0),
               "raw_change_pp": 100 * (safe_div(previous.get(reason, 0), previous_n) -
                                       safe_div(current.get(reason, 0), current_n)),
               "change_pp": round(100 * (safe_div(previous.get(reason, 0), previous_n) -
                                         safe_div(current.get(reason, 0), current_n)), 2)}
              for reason in REASONS]
    causes.sort(key=lambda item: item["change_pp"])

    column, table, id_col = DIMENSIONS[dimension]
    segments = []
    for period, period_start, period_end in (("current", start, end),
                                              ("previous", previous_start, previous_end)):
        segment_query = """
            SELECT %s AS id, d.name AS name,
              COUNT(*) AS orders, SUM(f.otif) AS otif_count,
              SUM(CASE WHEN f.otif=0 THEN 1 ELSE 0 END) AS misses
            FROM mart_order_fulfillment f JOIN dim_product p ON p.product_id=f.product_id
            JOIN %s d ON d.%s=%s
            WHERE f.order_date BETWEEN ? AND ? %s GROUP BY id, d.name
        """ % (column, table, id_col, column, clause)
        for row in rows(con, segment_query, [period_start, period_end] + args):
            row["period"] = period
            segments.append(row)
    grouped = defaultdict(dict)
    for item in segments:
        grouped[item["id"]][item["period"]] = item
    drilldown = []
    for identifier, period_rows in grouped.items():
        c, p = period_rows.get("current", {}), period_rows.get("previous", {})
        drilldown.append({
            "id": identifier, "name": c.get("name") or p.get("name"),
            "orders": c.get("orders", 0),
            "otif": round(100 * safe_div(c.get("otif_count", 0), c.get("orders", 0)), 1),
            "previous_otif": round(100 * safe_div(p.get("otif_count", 0), p.get("orders", 0)), 1),
            "raw_change_pp": 100 * (safe_div(p.get("misses", 0), previous_n) -
                                    safe_div(c.get("misses", 0), current_n)),
            "change_pp": round(100 * (safe_div(p.get("misses", 0), previous_n) -
                                      safe_div(c.get("misses", 0), current_n)), 2),
        })
    drilldown.sort(key=lambda item: item["change_pp"])
    return {"causes": causes, "segments": drilldown, "dimension": dimension,
            "total_change_pp": round(100 * (safe_div(current.get("On time in full", 0), current_n) -
                                            safe_div(previous.get("On time in full", 0), previous_n)), 2),
            "current_orders": current_n, "previous_orders": previous_n}


def trend(con, start, end, filters):
    clause, args = filters_sql(filters)
    return rows(con, """
        SELECT d.week_start AS week, COUNT(*) AS orders,
          ROUND(100.0*SUM(f.otif)/COUNT(*),1) AS otif,
          ROUND(100.0*SUM(f.backordered)/COUNT(*),1) AS backorder_rate
        FROM mart_order_fulfillment f JOIN dim_product p ON p.product_id=f.product_id
        JOIN dim_date d ON d.date_key=f.order_date
        WHERE f.order_date BETWEEN ? AND ?
    """ + clause + " GROUP BY d.week_start ORDER BY d.week_start", [start, end] + args)


def _z_alert(metric, entity, label, baseline, recent, unit, bad_direction="high", basis="mean"):
    if len(baseline) < 12 or len(recent) < 3:
        return None
    mean = statistics.mean(baseline)
    sigma = statistics.stdev(baseline) if len(baseline) > 1 else 0
    if sigma < 0.001:
        return None
    recent_mean = statistics.mean(recent)
    z = (recent_mean - mean) / sigma
    if (z < 2.5 if bad_direction == "high" else z > -2.5):
        return None
    return {"metric": metric, "entity": entity, "label": label,
            "baseline": round(mean, 2), "recent": round(recent_mean, 2),
            "z_score": round(z, 1), "unit": unit, "basis": basis,
            "severity": "critical" if abs(z) >= 3 else "warning",
            "message": "%s %s is %.1fσ %s its 90-day baseline" %
                       (label, metric.lower(), abs(z), "above" if z > 0 else "below")}


def anomalies(con, end):
    end_day = dt.date.fromisoformat(end)
    recent_start = (end_day - dt.timedelta(days=13)).isoformat()
    baseline_start = (end_day - dt.timedelta(days=103)).isoformat()
    baseline_end = (end_day - dt.timedelta(days=14)).isoformat()
    alerts = []
    specs = [
        ("Supplier lead time", "days", "supplier", """
            SELECT supplier_id AS entity, received_date AS date_key,
              julianday(received_date)-julianday(order_date) AS value
            FROM fact_purchase_orders WHERE received_date BETWEEN ? AND ?"""),
        ("Defect rate", "%", "plant", """
            SELECT r.plant_id AS entity, r.date_key,
              100.0*COALESCE(d.defects,0)/NULLIF(r.good_units,0) AS value
            FROM fact_production_runs r LEFT JOIN
              (SELECT run_id,SUM(defect_qty) AS defects FROM fact_defects GROUP BY run_id) d
              ON d.run_id=r.run_id WHERE r.date_key BETWEEN ? AND ?"""),
        ("Production downtime", "min", "plant", """
            SELECT plant_id AS entity, date_key, downtime_minutes AS value
            FROM fact_production_runs WHERE date_key BETWEEN ? AND ?"""),
        ("Shipping delay", "days", "geography", """
            SELECT o.geography_id AS entity, o.order_date AS date_key,
              MAX(0,julianday(s.delivery_date)-julianday(o.promised_date)) AS value
            FROM fact_orders o JOIN fact_shipments s ON s.order_id=o.order_id
            WHERE o.order_date BETWEEN ? AND ?"""),
    ]
    names = {}
    for table, key in (("dim_supplier", "supplier_id"), ("dim_plant", "plant_id"),
                       ("dim_geography", "geography_id"), ("dim_product", "product_id")):
        names.update({row[key]: row["name"] for row in rows(con, "SELECT %s,name FROM %s" % (key, table))})
    for metric, unit, _, sql in specs:
        grouped = defaultdict(lambda: {"baseline": [], "recent": []})
        for row in rows(con, sql, [baseline_start, end]):
            key = "baseline" if row["date_key"] <= baseline_end else "recent"
            if row["value"] is not None:
                grouped[row["entity"]][key].append(row["value"])
        for entity, values in grouped.items():
            observed = values["recent"]
            basis = "mean"
            if metric == "Shipping delay" and observed:
                observed = [max(observed)] * 3
                basis = "peak"
            result = _z_alert(metric, entity, "%s · %s" % (entity, names.get(entity, entity)),
                              values["baseline"], observed, unit, basis=basis)
            if result:
                alerts.append(result)

    # Inventory movements are day-to-day unit changes, grouped by SKU and DC.
    inventory = rows(con, """
        SELECT date_key, product_id, warehouse_id, on_hand_qty
        FROM fact_inventory_snapshot WHERE date_key BETWEEN ? AND ?
        ORDER BY product_id, warehouse_id, date_key
    """, [baseline_start, end])
    grouped = defaultdict(list)
    for row in inventory:
        grouped[(row["product_id"], row["warehouse_id"])].append(row)
    for (product, warehouse), series in grouped.items():
        changes = [(series[j]["date_key"], series[j]["on_hand_qty"] - series[j-1]["on_hand_qty"])
                   for j in range(1, len(series))]
        base = [v for day, v in changes if day <= baseline_end]
        recent = [v for day, v in changes if day >= recent_start]
        # An abrupt movement is an event anomaly, so compare the most negative
        # recent day with the distribution of baseline daily movements.
        result = _z_alert("Inventory movement", "%s/%s" % (product, warehouse),
                          "%s · %s" % (product, names.get(product, product)), base,
                          [min(recent)] * 3 if recent else [], "units", bad_direction="low", basis="peak")
        if result:
            alerts.append(result)
    alerts.sort(key=lambda a: abs(a["z_score"]), reverse=True)
    return alerts[:12]


def inventory_risks(con, end, filters):
    clauses, args = [], []
    for key, col in (("product", "i.product_id"), ("warehouse", "i.warehouse_id"),
                     ("material", "p.material_id")):
        if filters.get(key):
            clauses.append(col + "=?")
            args.append(filters[key])
    where = " AND " + " AND ".join(clauses) if clauses else ""
    result = rows(con, """
        SELECT i.product_id, p.name AS product, i.warehouse_id, w.name AS warehouse,
          i.on_hand_qty, i.allocated_qty, i.units_sold,
          ROUND(1.0*MAX(0,i.on_hand_qty-i.allocated_qty)/NULLIF(i.units_sold,0),1) AS days_cover,
          i.stockout_flag
        FROM fact_inventory_snapshot i JOIN dim_product p ON p.product_id=i.product_id
        JOIN dim_warehouse w ON w.warehouse_id=i.warehouse_id
        WHERE i.date_key=? %s ORDER BY days_cover ASC LIMIT 8
    """ % where, [end] + args)
    return result


def supplier_scorecard(con, start, end, filters):
    clause, args = filters_sql(filters)
    return rows(con, """
        SELECT f.supplier_id AS id, s.name, COUNT(*) AS orders,
          ROUND(100.0*SUM(f.otif)/COUNT(*),1) AS otif,
          ROUND(100.0*SUM(CASE WHEN f.primary_failure_reason='Supplier delays' THEN 1 ELSE 0 END)/COUNT(*),1)
            AS supplier_delay_rate
        FROM mart_order_fulfillment f JOIN dim_product p ON p.product_id=f.product_id
        JOIN dim_supplier s ON s.supplier_id=f.supplier_id
        WHERE f.order_date BETWEEN ? AND ? %s
        GROUP BY f.supplier_id,s.name ORDER BY otif ASC
    """ % clause, [start, end] + args)


def demand_forecast(con, end, filters):
    end_day = dt.date.fromisoformat(end)
    history_start = (end_day - dt.timedelta(days=55)).isoformat()
    clauses, args = [], []
    for key, col in (("product", "x.product_id"), ("warehouse", "x.warehouse_id"),
                     ("material", "p.material_id")):
        if filters.get(key):
            clauses.append(col + "=?")
            args.append(filters[key])
    where = " AND " + " AND ".join(clauses) if clauses else ""
    history = rows(con, """
        SELECT x.date_key,x.product_id,p.name AS product,x.warehouse_id,
          x.actual_demand,x.forecast_qty
        FROM fact_forecast x JOIN dim_product p ON p.product_id=x.product_id
        WHERE x.date_key BETWEEN ? AND ? %s ORDER BY x.date_key
    """ % where, [history_start, end] + args)
    grouped = defaultdict(list)
    for row in history:
        grouped[(row["product_id"], row["warehouse_id"], row["product"])].append(row)
    forecasts = []
    for (product, warehouse, name), series in grouped.items():
        recent = series[-28:]
        prior = series[-56:-28]
        if len(recent) < 14:
            continue
        recent_mean = statistics.mean(x["actual_demand"] for x in recent)
        prior_mean = statistics.mean(x["actual_demand"] for x in prior) if prior else recent_mean
        trend = max(-0.2, min(0.2, safe_div(recent_mean - prior_mean, prior_mean)))
        weekday = defaultdict(list)
        for row in recent:
            weekday[dt.date.fromisoformat(row["date_key"]).weekday()].append(row["actual_demand"])
        predicted = []
        for offset in range(1, 15):
            day = end_day + dt.timedelta(days=offset)
            weekday_mean = statistics.mean(weekday[day.weekday()]) if weekday[day.weekday()] else recent_mean
            predicted.append(max(0, round((0.65 * weekday_mean + 0.35 * recent_mean) * (1 + trend))))
        forecasts.append({"product_id": product, "product": name, "warehouse_id": warehouse,
                          "next_14_days": sum(predicted), "daily": predicted,
                          "recent_28_days": sum(x["actual_demand"] for x in recent),
                          "forecast_bias_pct": round(100 * safe_div(
                              sum(x["forecast_qty"] - x["actual_demand"] for x in recent),
                              sum(x["actual_demand"] for x in recent)), 1)})
    forecasts.sort(key=lambda item: item["next_14_days"], reverse=True)
    return forecasts


def filter_options(con):
    options = {}
    for dimension, (_, table, key) in DIMENSIONS.items():
        options[dimension] = rows(con, "SELECT %s AS id,name FROM %s ORDER BY name" % (key, table))
    options["warehouse"] = rows(con, "SELECT warehouse_id AS id,name FROM dim_warehouse ORDER BY name")
    return options


def overview(con, days=28, end=None, filters=None, dimension="supplier"):
    filters = filters or {}
    days = max(7, min(90, int(days)))
    start, end, prev_start, prev_end = period_bounds(con, days, end)
    current, count = kpis(con, start, end, filters)
    previous, prev_count = kpis(con, prev_start, prev_end, filters)
    bridge = root_cause(con, start, end, prev_start, prev_end, filters, dimension)
    trend_start = (dt.date.fromisoformat(end) - dt.timedelta(days=83)).isoformat()
    return {
        "period": {"start": start, "end": end, "days": days,
                   "previous_start": prev_start, "previous_end": prev_end,
                   "orders": count, "previous_orders": prev_count},
        "kpis": current, "previous_kpis": previous,
        "root_cause": bridge,
        "trend": trend(con, trend_start, end, filters),
        "anomalies": anomalies(con, end),
        "inventory_risks": inventory_risks(con, end, filters),
        "suppliers": supplier_scorecard(con, start, end, filters),
        "forecast": demand_forecast(con, end, filters),
        "filters": filter_options(con),
    }
