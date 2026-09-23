"""Dependency-free HTTP API and static dashboard server."""

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .analytics import DIMENSIONS, connect, overview
from .report import executive_report
from .seed import DEFAULT_DB, seed_database

WEB = Path(__file__).resolve().parent / "web"


def make_handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        def send_bytes(self, content, mime, status=200):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path in ("/api/overview", "/api/report", "/api/health"):
                try:
                    if path == "/api/health":
                        payload = {"status": "ok", "database": str(db_path)}
                        self.send_bytes(json.dumps(payload).encode(), "application/json")
                        return
                    query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
                    end = query.get("end")
                    con = connect(db_path)
                    try:
                        if path == "/api/report":
                            report = executive_report(con, end)
                            self.send_bytes(report["html"].encode(), "text/html; charset=utf-8")
                        else:
                            filters = {key: query[key] for key in
                                       ("supplier", "plant", "geography", "product", "material", "warehouse")
                                       if query.get(key)}
                            dimension = query.get("dimension", "supplier")
                            if dimension not in DIMENSIONS:
                                raise ValueError("Unknown drilldown dimension")
                            data = overview(con, int(query.get("days", 28)), end, filters, dimension)
                            self.send_bytes(json.dumps(data).encode(), "application/json; charset=utf-8")
                    finally:
                        con.close()
                except (ValueError, OSError) as exc:
                    self.send_bytes(json.dumps({"error": str(exc)}).encode(), "application/json", 400)
                return
            static = {"/": "index.html", "/index.html": "index.html",
                      "/app.js": "app.js", "/styles.css": "styles.css"}
            if path not in static:
                self.send_error(404)
                return
            file = WEB / static[path]
            mime = mimetypes.guess_type(str(file))[0] or "application/octet-stream"
            if path.endswith(".js") or path.endswith(".css") or path.endswith(".html"):
                mime += "; charset=utf-8"
            self.send_bytes(file.read_bytes(), mime)

        def log_message(self, format, *args):
            print("%s - %s" % (self.address_string(), format % args))

    return Handler


def serve(host="127.0.0.1", port=8000, db=DEFAULT_DB):
    db = Path(db)
    if not db.exists():
        print("No database found. Building the sample database...")
        seed_database(db)
    server = ThreadingHTTPServer((host, port), make_handler(db))
    print("OpsVision running at http://%s:%s" % (host, port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run OpsVision dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    serve(args.host, args.port, args.db)
