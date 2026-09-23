import datetime as dt
import tempfile
import unittest
from pathlib import Path

from opsvision.analytics import connect, overview
from opsvision.report import executive_report
from opsvision.seed import seed_database
from opsvision.export import export_csv
from opsvision.ingest import ingest_csv


class AnalyticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.tmp.name) / "test.db"
        seed_database(cls.db, as_of=dt.date(2026, 9, 23))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_otif_bridge_reconciles_at_order_grain(self):
        con = connect(self.db)
        data = overview(con)
        con.close()
        self.assertEqual(data["kpis"]["otif"], 86.0)
        self.assertEqual(data["previous_kpis"]["otif"], 94.0)
        self.assertEqual(data["root_cause"]["total_change_pp"], -8.0)
        self.assertAlmostEqual(sum(item["raw_change_pp"] for item in data["root_cause"]["causes"]), -8.0)
        self.assertAlmostEqual(sum(item["raw_change_pp"] for item in data["root_cause"]["segments"]), -8.0)

    def test_scope_and_anomalies(self):
        con = connect(self.db)
        all_data = overview(con)
        plant = overview(con, filters={"plant": "P02"}, dimension="plant")
        con.close()
        self.assertLess(plant["period"]["orders"], all_data["period"]["orders"])
        self.assertLess(plant["kpis"]["otif"], all_data["kpis"]["otif"])
        self.assertTrue({"Supplier lead time", "Inventory movement", "Defect rate",
                         "Production downtime", "Shipping delay"}.issubset(
                             {item["metric"] for item in all_data["anomalies"]}))
        self.assertTrue(all(item["forecast_bias_pct"] is not None for item in all_data["forecast"]))

    def test_report_and_referential_integrity(self):
        con = connect(self.db)
        self.assertEqual(list(con.execute("PRAGMA foreign_key_check")), [])
        report = executive_report(con)
        con.close()
        self.assertIn("Supply Chain Executive Report", report["html"])
        self.assertIn("Suppliers to review", report["markdown"])
        self.assertIn("sample operations data", report["html"])

    def test_csv_round_trip_preserves_service_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            csv_dir = Path(folder) / "csv"
            target = Path(folder) / "imported.db"
            export_csv(self.db, csv_dir)
            counts = ingest_csv(csv_dir, target)
            con = connect(target)
            restored = overview(con)
            con.close()
            self.assertEqual(counts["fact_orders"], 4900)
            self.assertEqual(restored["kpis"]["otif"], 86.0)
            self.assertEqual(restored["root_cause"]["total_change_pp"], -8.0)


if __name__ == "__main__":
    unittest.main()
