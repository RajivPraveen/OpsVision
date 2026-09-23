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


def delta_pp(current, previous):
    change = round(current - previous, 1)
    return "%+.1f pp" % (0.0 if change == 0 else change)


def executive_report(con, end=None):
    data = overview(con, days=7, end=end)
    period = data["period"]
    k, old = data["kpis"], data["previous_kpis"]
    headline = [
        ("OTIF", fmt(k["otif"]), delta_pp(k["otif"], old["otif"])),
        ("Fill rate", fmt(k["fill_rate"]), delta_pp(k["fill_rate"], old["fill_rate"])),
        ("Stockout rate", fmt(k["stockout_rate"]), delta_pp(k["stockout_rate"], old["stockout_rate"])),
        ("Forecast accuracy", fmt(k["forecast_accuracy"]), delta_pp(k["forecast_accuracy"], old["forecast_accuracy"])),
        ("Production downtime", fmt(k["production_downtime"]),
         delta_pp(k["production_downtime"], old["production_downtime"])),
    ]
    causes = [x for x in data["root_cause"]["causes"] if x["change_pp"] != 0]
    suppliers = [x for x in data["suppliers"] if x["orders"] >= 5][:3]
    inventory = data["inventory_risks"][:5]
    deviations = sorted(data["forecast"], key=lambda x: abs(x["forecast_bias_pct"]), reverse=True)[:5]
    title = "Supply Chain Executive Report · %s to %s" % (period["start"], period["end"])
    e = html.escape
    def list_items(items):
        return "".join("<li>%s</li>" % e(item) for item in items) or "<li>No material issues detected.</li>"
    cause_lines = ["%s: %+.2f percentage points (%s vs %s misses)" %
                   (x["reason"], x["change_pp"], x["current_count"], x["previous_count"]) for x in causes]
    distinct_anomalies = []
    for alert in data["anomalies"]:
        if all(existing["metric"] != alert["metric"] for existing in distinct_anomalies):
            distinct_anomalies.append(alert)
    anomaly_lines = ["%s: %s %.1f%s is %.1fσ from baseline %.1f%s" %
                     (x["label"], "peak" if x["basis"] == "peak" else "recent mean",
                      x["recent"], unit_suffix(x["unit"]), x["z_score"],
                      x["baseline"], unit_suffix(x["unit"])) for x in distinct_anomalies[:5]]
    supplier_lines = ["%s (%s): %.1f%% OTIF across %s order lines" %
                      (x["name"], x["id"], x["otif"], x["orders"]) for x in suppliers]
    inventory_lines = ["%s at %s: %s available, %.1f days of cover" %
                       (x["product"], x["warehouse"], x["on_hand_qty"] - x["allocated_qty"],
                        x["days_cover"] or 0) for x in inventory]
    forecast_lines = ["%s at %s: %+0.1f%% forecast bias; %s units expected next 14 days" %
                      (x["product"], x["warehouse_id"], x["forecast_bias_pct"],
                       x["next_14_days"]) for x in deviations]
    cards = "".join("<div class='card'><span>%s</span><strong>%s</strong><em>%s vs prior week</em></div>" %
                    (e(name), e(value), e(delta)) for name, value, delta in headline)
    sections = [
        ("OTIF driver bridge", cause_lines),
        ("Statistical anomalies", anomaly_lines),
        ("Suppliers to review", supplier_lines),
        ("Inventory risks", inventory_lines),
        ("Demand and forecast deviations", forecast_lines),
    ]
    section_html = "".join("<section><h2>%s</h2><ul>%s</ul></section>" %
                           (e(name), list_items(items)) for name, items in sections)
    document = """<!doctype html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>%s</title><style>
@page{size:A4;margin:20mm}*{box-sizing:border-box}body{margin:0;background:#edf2f4;
font:15px/1.55 system-ui,-apple-system,sans-serif;color:#153044}.page{max-width:960px;
margin:32px auto;padding:48px;background:white;box-shadow:0 15px 45px #17334a18}
.eyebrow{color:#008a91;text-transform:uppercase;letter-spacing:.16em;font-weight:800;font-size:11px}
h1{font-size:32px;line-height:1.18;margin:12px 0}h2{font-size:17px;margin:0 0 12px;color:#17344c}
.sub{color:#667b89}.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:28px 0}
.card{border:1px solid #dce5e9;padding:14px;border-radius:8px}.card span{display:block;
font-size:11px;color:#607582}.card strong{display:block;font-size:23px;margin:4px 0}
.card em{font-style:normal;font-size:11px;color:#465e6a}section{border-top:1px solid #e1e8eb;
padding:20px 0 8px}li{padding:4px 0}footer{margin-top:20px;color:#82949b;font-size:11px}
@media print{body{background:white}.page{margin:0;padding:0;box-shadow:none}}
</style></head><body><main class='page'><div class='eyebrow'>OpsVision / Weekly report</div>
<h1>%s</h1><div class='sub'>%s order lines · comparison: %s to %s · sample operations data</div>
<div class='cards'>%s</div>%s<footer>Each late or short order has one recorded reason. Those reasons add up to the change in on-time, in-full delivery.
Alerts compare the latest 14 days with the previous 90 days.</footer>
</main></body></html>""" % (e(title), e(title), period["orders"],
                              period["previous_start"], period["previous_end"], cards, section_html)
    markdown = "# %s\n\nSample operations data. %s order lines.\n\n" % (title, period["orders"])
    markdown += "## KPI changes\n\n" + "\n".join("- %s: %s (%s)" % row for row in headline) + "\n\n"
    for name, items in sections:
        markdown += "## %s\n\n%s\n\n" % (name, "\n".join("- " + item for item in items) or "- No material issues detected.")
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
