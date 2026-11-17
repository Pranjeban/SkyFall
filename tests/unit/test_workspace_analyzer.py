from __future__ import annotations

import unittest
from pathlib import Path

from skyfall_workspace.analyzer import analyze_file, detect_sensitive_content


class WorkspaceAnalyzerTests(unittest.TestCase):
    def test_detects_common_secret_assignments(self) -> None:
        samples = [
            'client_secret = "test-secret-value-12345"',
            'password: "test-password-value-12345"',
            'api_key = "test-api-key-value-12345"',
            'Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456',
            'github_pat_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
            '<add key="ApiKey" value="test-api-key-value-12345" />',
            'AccountKey=abcdefghijklmnopqrstuvwxyz1234567890',
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(detect_sensitive_content(sample))

    def test_does_not_flag_ordinary_source_metadata(self) -> None:
        sample = (
            "param([string]$EnvironmentName)\n"
            "function Get-Inventory { return @() }\n"
            "Import-Module Az.Accounts\n"
        )
        self.assertFalse(detect_sensitive_content(sample))

    def test_python_syntax_error_summary_is_not_misleading(self) -> None:
        result = analyze_file(
            Path("broken.py"),
            "def broken(:\n    pass\n",
        )
        self.assertTrue(result["parse_status"].startswith("syntax_error"))
        self.assertIn("could not be parsed", result["summary"])
        self.assertEqual(result["functions"], [])

    def test_deeply_nested_json_is_reported_as_unparseable(self) -> None:
        deeply_nested = "[" * 10000 + "0" + "]" * 10000
        result = analyze_file(Path("deep.json"), deeply_nested)
        self.assertIn("could not be parsed", result["summary"])

    def test_markdown_extraction_returns_heading_names_not_body_text(self) -> None:
        result = analyze_file(
            Path("README.md"),
            "# Inventory Automation\n\nThis paragraph contains private project details.\n",
        )
        self.assertEqual(result["top_level_keys_or_headings"], ["Inventory Automation"])
        self.assertNotIn("private project details", result["summary"])


if __name__ == "__main__":
    unittest.main()
