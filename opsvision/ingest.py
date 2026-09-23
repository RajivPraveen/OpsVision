"""Load schema-shaped operational CSV extracts into a fresh SQLite mart."""

import csv
import sqlite3
from pathlib import Path

from .export import TABLES
from .seed import DEFAULT_DB

FACT_AND_DIMENSION_TABLES = [name for name in TABLES if not name.startswith("mart_")]


def ingest_csv(input_dir, db=DEFAULT_DB):
    input_dir, db = Path(input_dir), Path(db)
    if db.exists():
        raise FileExistsError("Database already exists: %s. Choose a new --db path." % db)
    db.parent.mkdir(parents=True, exist_ok=True)
    missing = [name for name in FACT_AND_DIMENSION_TABLES if not (input_dir / (name + ".csv")).exists()]
    if missing:
        raise FileNotFoundError("Missing CSV tables: " + ", ".join(missing))
    con = sqlite3.connect(str(db))
    try:
        con.executescript(Path(__file__).with_name("schema.sql").read_text())
        counts = {}
        for table in FACT_AND_DIMENSION_TABLES:
            with (input_dir / (table + ".csv")).open(newline="", encoding="utf-8-sig") as file:
                reader = csv.DictReader(file)
                columns = [item[1] for item in con.execute("PRAGMA table_info(%s)" % table)]
                if reader.fieldnames != columns:
                    raise ValueError("Column mismatch in %s.csv. Expected: %s" % (table, ", ".join(columns)))
                records = [[row[col] if row[col] != "" else None for col in columns] for row in reader]
            placeholders = ",".join("?" for _ in columns)
            con.executemany("INSERT INTO %s VALUES (%s)" % (table, placeholders), records)
            counts[table] = len(records)
        violations = list(con.execute("PRAGMA foreign_key_check"))
        if violations:
            raise ValueError("Foreign-key violations: %s" % violations[:5])
        con.commit()
        return counts
    except Exception:
        con.close()
        db.unlink(missing_ok=True)
        raise
    finally:
        try:
            con.close()
        except Exception:
            pass
