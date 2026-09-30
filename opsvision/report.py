"""Executive report generator. Outputs a portable HTML document and Markdown."""

import argparse
import datetime as dt
import html
from pathlib import Path

from .analytics import connect, overview
from .seed import DEFAULT_DB

ROOT = Path.cwd()


def fmt(value, suffix="%"):
    return "%.1f%s" % (value, suffix)


def unit_suffix(unit):
    return unit if unit == "%" else " " + unit


def change_text(current, previous, higher_is_better, suffix=" points"):
    """Plain-English change, e.g. '8.0 points worse' or 'no change'."""
    change = round(current - previous, 1)
    if change == 0:
        return "no change"
    better = (change > 0) == higher_is_better
    return "%s %.1f%s %s" % ("▲" if change > 0 else "▼", abs(change), suffix, "better" if better else "worse")


def executive_report(con, end=None):
    data = overview(con, days=7, end=end)
    period = data["period"]
    k, old = data["kpis"], data["previous_kpis"]
    headline = [
        ("Delivered on time and complete", fmt(k["otif"]), change_text(k["otif"], old["otif"], True)),
        ("Units shipped of units ordered", fmt(k["fill_rate"]), change_text(k["fill_rate"], old["fill_rate"], True)),
        ("Out of stock", fmt(k["stockout_rate"]), change_text(k["stockout_rate"], old["stockout_rate"], False)),
        ("Forecast accuracy", fmt(k["forecast_accuracy"]),
         change_text(k["forecast_accuracy"], old["forecast_accuracy"], True)),
        ("Production time lost to stoppages", fmt(k["production_downtime"]),
         change_text(k["production_downtime"], old["production_downtime"], False)),
    ]
    causes = [x for x in data["root_cause"]["causes"] if x["change_pp"] != 0]
    worst = sorted((x for x in causes if x["change_pp"] < 0), key=lambda x: x["change_pp"])
    delta = data["root_cause"]["total_change_pp"]
    summary = "%.0f%% of order lines arrived on time and complete this week, %s %.0f%% the week before (target: 95%%)." % (
        k["otif"], "down from" if delta < 0 else "up from" if delta > 0 else "the same as", old["otif"])
    if delta < 0 and worst:
        summary += " The biggest cause was %s (%.1f of the %.1f points)." % (
            worst[0]["reason"].lower(), abs(worst[0]["change_pp"]), abs(delta))
    suppliers = [x for x in data["suppliers"] if x["orders"] >= 5][:3]
    inventory = data["inventory_risks"][:5]
    deviations = sorted(data["forecast"], key=lambda x: abs(x["forecast_bias_pct"]), reverse=True)[:5]
    title = "Supply Chain Executive Report · %s to %s" % (period["start"], period["end"])
    e = html.escape

    def list_items(items):
        return "".join("<li>%s</li>" % e(item) for item in items) or "<li>Nothing to flag.</li>"

    cause_lines = ["%s: %s%.2f points (%s late or short orders, %s the week before)" %
                   (x["reason"], "+" if x["change_pp"] > 0 else "−", abs(x["change_pp"]),
                    x["current_count"], x["previous_count"]) for x in causes]
    distinct_anomalies = []
    for alert in data["anomalies"]:
        if all(existing["metric"] != alert["metric"] for existing in distinct_anomalies):
            distinct_anomalies.append(alert)
    anomaly_lines = ["%s, %s: %s %.1f%s against a usual %.1f%s (%.1f× its normal variation)" %
                     (x["metric"], x["label"].split(" · ", 1)[-1],
                      "peaked at" if x["basis"] == "peak" else "averaging",
                      x["recent"], unit_suffix(x["unit"]), x["baseline"], unit_suffix(x["unit"]),
                      abs(x["z_score"])) for x in distinct_anomalies[:5]]
    supplier_lines = ["%s: %.1f%% of order lines on time and complete (%s order lines)" %
                      (x["name"], x["otif"], x["orders"]) for x in suppliers]
    inventory_lines = ["%s at %s: %s units available, %.1f days left" %
                       (x["product"], x["warehouse"], x["on_hand_qty"] - x["allocated_qty"],
                        x["days_cover"] or 0) for x in inventory]
    forecast_lines = ["%s at %s: forecasts ran %s by %.1f%%; %s units expected in the next 14 days" %
                      (x["product"], x["warehouse_id"], "high" if x["forecast_bias_pct"] > 0 else "low",
                       abs(x["forecast_bias_pct"]), x["next_14_days"]) for x in deviations]
    cards = "".join("<div class='card'><span>%s</span><strong>%s</strong><em>%s vs. the week before</em></div>" %
                    (e(name), e(value), e(delta)) for name, value, delta in headline)
    sections = [
        ("Why delivery changed", cause_lines),
        ("Unusual changes", anomaly_lines),
        ("Suppliers to review", supplier_lines),
        ("Stock running low", inventory_lines),
        ("Demand and forecast misses", forecast_lines),
    ]
    section_html = "".join("<section><h2>%s</h2><ul>%s</ul></section>" %
                           (e(name), list_items(items)) for name, items in sections)
    document = """<!doctype html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>%s</title><style>
@page{size:A4;margin:20mm}*{box-sizing:border-box}body{margin:0;background:#f6f6f4;
font:15px/1.55 Inter,system-ui,-apple-system,sans-serif;color:#1d2127}.page{max-width:960px;
margin:32px auto;padding:44px 48px;background:white;border:1px solid #e7e7e3;border-radius:12px}
.eyebrow{color:#b45309;text-transform:uppercase;letter-spacing:.12em;font-weight:600;font-size:11px}
h1{font-size:28px;line-height:1.2;font-weight:650;margin:8px 0 6px}h2{font-size:16px;font-weight:650;margin:0 0 8px}
.sub{color:#8a9099;font-size:13px}.answer{margin:18px 0 0;padding:12px 16px;border:1px solid #e7e7e3;
border-left:3px solid #b45309;border-radius:8px;color:#4d5560}
.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:22px 0}
.card{border:1px solid #e7e7e3;padding:12px 14px;border-radius:10px}.card span{display:block;
font-size:12px;color:#4d5560;line-height:1.35}.card strong{display:block;font-size:22px;font-weight:650;margin:4px 0}
.card em{display:block;font-style:normal;font-size:11.5px;line-height:1.4;color:#8a9099}section{border-top:1px solid #e7e7e3;
padding:16px 0 6px}ul{margin:0;padding-left:18px;color:#4d5560}li{padding:3px 0}
footer{margin-top:16px;color:#8a9099;font-size:12px}
@media print{body{background:white}.page{margin:0;padding:0;border:0}}
</style></head><body><main class='page'><div class='eyebrow'>OpsVision · weekly report</div>
<h1>%s</h1><div class='sub'>%s order lines · compared with %s to %s · sample operations data</div>
<p class='answer'>%s</p>
<div class='cards'>%s</div>%s<footer>Each late or incomplete order records one main reason; those reasons add up to the change
in on-time, complete delivery. Unusual changes compare the latest 14 days with the 90 days before.</footer>
</main></body></html>""" % (e(title), e(title), period["orders"],
                              period["previous_start"], period["previous_end"], e(summary), cards, section_html)
    markdown = "# %s\n\nSample operations data. %s order lines.\n\n%s\n\n" % (title, period["orders"], summary)
    markdown += "## Key numbers\n\n" + "\n".join("- %s: %s (%s)" % row for row in headline) + "\n\n"
    for name, items in sections:
        markdown += "## %s\n\n%s\n\n" % (name, "\n".join("- " + item for item in items) or "- Nothing to flag.")
    return {"html": document, "markdown": markdown, "title": title, "data": data}


def write_report(db=DEFAULT_DB, output_dir=ROOT / "reports", end=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    con = connect(db)
    report = executive_report(con, end)
    con.close()
    date = report["data"]["period"]["end"]
    html_path = output_dir / ("executive-report-%s.html" % date)
    md_path = output_dir / ("executive-report-%s.md" % date)
    html_path.write_text(report["html"], encoding="utf-8")
    md_path.write_text(report["markdown"], encoding="utf-8")
    return html_path, md_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate weekly executive report")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--end", type=dt.date.fromisoformat)
    args = parser.parse_args()
    for path in write_report(args.db, args.output_dir, args.end.isoformat() if args.end else None):
        print(path)
