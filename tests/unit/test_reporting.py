from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from skyfall_cloud.reporting import (
    ReportExporter,
    prepare_report,
    write_csv_report,
    write_json_report,
    write_markdown_report,
    write_report,
)


class ReportingTests(unittest.TestCase):
    def sample(self):
        return [
            {"name": "alpha", "count": 2},
            {"name": "beta", "count": 3},
        ]

    def test_prepare_report_schema(self):
        report = prepare_report(title="Demo", rows=self.sample())
        self.assertEqual(report["schema_version"], "1.0")
        self.assertEqual(report["title"], "Demo")
        self.assertEqual(report["columns"], ["name", "count"])
        self.assertEqual(len(report["rows"]), 2)
        self.assertEqual(report["summary"]["row_count"], 2)

    def test_csv_json_markdown_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            report = prepare_report(title="Demo", rows=self.sample(), metadata={"source": "test"})
            csv_path = write_csv_report(base / "out.csv", report=report)
            json_path = write_json_report(base / "out.json", report=report)
            md_path = write_markdown_report(base / "out.md", report=report)

            with open(csv_path, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["name"], "alpha")

            payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["metadata"]["source"], "test")
            self.assertEqual(payload["columns"], ["name", "count"])

            markdown = Path(md_path).read_text(encoding="utf-8")
            self.assertIn("# Demo", markdown)
            self.assertIn("| name | count |", markdown)
            self.assertIn("alpha", markdown)

    def test_write_report_format_dispatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            returned = write_report(path, output_format="json", title="X", rows=self.sample())
            self.assertEqual(returned, str(path))
            self.assertTrue(path.is_file())

    def test_exporter_aliases(self):
        exporter = ReportExporter(title="E", rows=self.sample())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "e.csv"
            exporter.export_csv(path)
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
