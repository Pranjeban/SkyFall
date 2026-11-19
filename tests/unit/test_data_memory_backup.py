import shutil
import tempfile
import unittest
from pathlib import Path

from memory.data_memory_backup import (
    backup_data_memory,
    export_data_memory_json,
    import_data_memory_json,
)

SOURCE_DB = Path(r"C:\Users\pranj\OneDrive\Documents\Skyfall(1)\Skyfall\Data_Memory\skyfall_memory.sqlite3")


class DataMemoryBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work = Path(self.temp_dir.name)
        self.source_copy = self.work / "source.db"
        if SOURCE_DB.exists():
            shutil.copyfile(SOURCE_DB, self.source_copy)
        else:
            self.skipTest("source DB missing")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_backup_round_trip(self) -> None:
        backup_path = self.work / "backup.db"
        result = backup_data_memory(self.source_copy, backup_path)
        self.assertTrue(result.exists())
        self.assertGreater(result.stat().st_size, 0)

    def test_export_creates_json(self) -> None:
        export_path = self.work / "export.json"
        result = export_data_memory_json(self.source_copy, export_path)
        self.assertTrue(result.exists())
        import json
        with result.open() as f:
            payload = json.load(f)
        self.assertIn("conversations", payload)
        self.assertIn("messages", payload)
        self.assertIn("memory_documents", payload)

    def test_import_skip_conflict(self) -> None:
        export_path = self.work / "export.json"
        export_data_memory_json(self.source_copy, export_path)
        dest = self.work / "dest.db"
        backup_data_memory(self.source_copy, dest)
        result = import_data_memory_json(export_path, dest, on_conflict="skip")
        self.assertIn("imported", result)
        self.assertIn("skipped", result)


if __name__ == "__main__":
    unittest.main()
