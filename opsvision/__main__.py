"""Single entry point for the demo, report and server."""

import argparse
import datetime as dt
from pathlib import Path

from .report import write_report
from .export import export_csv
from .ingest import ingest_csv
from .seed import DEFAULT_DB, seed_database
from .server import serve


def main():
    parser = argparse.ArgumentParser(prog="python3 -m opsvision")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed", help="create reproducible synthetic SQLite data")
    seed.add_argument("--db", type=Path, default=DEFAULT_DB)
    seed.add_argument("--as-of", type=dt.date.fromisoformat)
    web = sub.add_parser("serve", help="launch local dashboard and API")
    web.add_argument("--db", type=Path, default=DEFAULT_DB)
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8000)
    report = sub.add_parser("report", help="write the weekly executive report")
    report.add_argument("--db", type=Path, default=DEFAULT_DB)
    report.add_argument("--output-dir", type=Path, default=Path("reports"))
    report.add_argument("--end", type=dt.date.fromisoformat)
    extract = sub.add_parser("export", help="export star-schema tables and order mart as CSV")
    extract.add_argument("--db", type=Path, default=DEFAULT_DB)
    extract.add_argument("--output-dir", type=Path, default=Path("exports"))
    ingest = sub.add_parser("ingest", help="load schema-shaped CSV extracts into a new database")
    ingest.add_argument("--input-dir", type=Path, required=True)
    ingest.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "seed":
        print(seed_database(args.db, args.as_of))
    elif args.command == "serve":
        serve(args.host, args.port, args.db)
    elif args.command == "report":
        for path in write_report(args.db, args.output_dir,
                                 args.end.isoformat() if args.end else None):
            print(path)
    elif args.command == "export":
        for path in export_csv(args.db, args.output_dir):
            print(path)
    elif args.command == "ingest":
        print(ingest_csv(args.input_dir, args.db))


if __name__ == "__main__":
    main()
