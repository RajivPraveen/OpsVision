# Local API

Start the server with:

~~~bash
python3 -m opsvision serve
~~~

The default address is **http://127.0.0.1:8000**. The API is intended for local use. It has no sign-in layer, so do not expose a database with company data on a public network without adding access controls.

## Dashboard data

**GET /api/overview** returns the current and prior measures, the delivery breakdown, weekly trend, alerts, stock risks, supplier list, demand outlook, and filter choices as JSON.

| Parameter | Example | What it does |
| --- | --- | --- |
| days | 28 | Length of both comparison periods; allowed range is 7–90 |
| end | 2026-09-13 | Last day to include; defaults to the latest order date |
| supplier | S042 | Show one supplier where that field exists |
| plant | P02 | Show one plant where that field exists |
| geography | G02 | Show one destination geography on orders |
| product | PR12 | Show one product |
| material | M03 | Show products made with one material |
| warehouse | W01 | Show one warehouse where that field exists |
| dimension | plant | Split the delivery change by supplier, plant, geography, product, or material |

Example:

~~~text
http://127.0.0.1:8000/api/overview?days=28&plant=P02&dimension=product
~~~

Selected fields in the response:

~~~json
{
  "period": {"start": "2026-08-17", "end": "2026-09-13", "orders": 700},
  "kpis": {"otif": 86.0},
  "previous_kpis": {"otif": 94.0},
  "root_cause": {
    "total_change_pp": -8.0,
    "causes": [],
    "segments": []
  },
  "trend": [],
  "anomalies": [],
  "inventory_risks": [],
  "suppliers": [],
  "forecast": []
}
~~~

The example shows the shape of the response, not the full response or the result of the plant filter.

## Weekly report

**GET /api/report** returns a printable HTML report for the latest seven days. Add an optional end date:

~~~text
http://127.0.0.1:8000/api/report?end=2026-09-13
~~~

## Health

**GET /api/health** returns a small JSON status response showing that the server is running and which database file it uses.

## Errors

Invalid dates or an unknown breakdown dimension return HTTP 400 with a JSON error message. A missing page returns HTTP 404.

