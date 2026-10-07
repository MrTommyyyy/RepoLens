import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repolens import inventory, mib, save_report


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_size_totals_extensions_and_deterministic_largest_files(self):
        (self.folder / "b.py").write_bytes(b"abc")
        (self.folder / "a.py").write_bytes(b"xyz")
        (self.folder / "README").write_bytes(b"a")
        report = inventory(self.folder, top=2)
        self.assertEqual((report["files"], report["bytes"]), (3, 7))
        self.assertEqual([item["path"] for item in report["largest_files"]], ["a.py", "b.py"])
        self.assertEqual(report["extensions"][".py"]["bytes"], 6)
        self.assertIn("[no extension]", report["extensions"])

    def test_generated_directories_and_custom_globs_excluded(self):
        (self.folder / "main.py").write_text("pass")
        for name in ("node_modules", ".git", ".venv", "dist", "private"):
            directory = self.folder / name
            directory.mkdir()
            (directory / "large.bin").write_bytes(b"x" * 100)
        (self.folder / "cache.log").write_text("skip")
        report = inventory(self.folder, excludes=["private", "*.log"])
        self.assertEqual(report["files"], 1)
        self.assertEqual(len(report["excluded_directories"]), 5)

    def test_symlink_file_and_directory_not_followed(self):
        (self.folder / "source.txt").write_text("hello")
        try:
            (self.folder / "copy.txt").symlink_to(self.folder / "source.txt")
            (self.folder / "loop").symlink_to(self.folder, target_is_directory=True)
        except OSError:
            self.skipTest("Symbolic links unavailable")
        report = inventory(self.folder)
        self.assertEqual(report["files"], 1)
        self.assertEqual(report["skipped_symlinks"], ["copy.txt", "loop"])

    def test_optional_lines_skip_binary_non_utf8_and_large_files(self):
        (self.folder / "main.py").write_bytes(b"first\nsecond")
        (self.folder / "empty.txt").write_bytes(b"")
        (self.folder / "binary.bin").write_bytes(b"a\x00b")
        (self.folder / "latin.txt").write_bytes(b"\xff")
        (self.folder / "big.txt").write_bytes(b"x" * 20)
        with patch("repolens.LINE_LIMIT", 16):
            report = inventory(self.folder, lines=True)
        self.assertEqual(report["line_statistics"], {"enabled": True, "files_counted": 2, "files_skipped": 3, "total_lines": 2})
        self.assertEqual(report["extensions"][".py"]["lines"], 2)

    def test_exact_size_budget_boundaries_and_failures(self):
        (self.folder / "a.txt").write_bytes(b"x" * 10)
        self.assertTrue(inventory(self.folder, max_file_bytes=10, max_total_bytes=10)["ok"])
        report = inventory(self.folder, max_file_bytes=9, max_total_bytes=9)
        self.assertFalse(report["ok"])
        self.assertEqual(report["budgets"]["oversized_files"][0]["path"], "a.txt")
        self.assertTrue(report["budgets"]["total_exceeded"])

    def test_empty_folder_and_invalid_options(self):
        self.assertEqual(inventory(self.folder)["files"], 0)
        self.assertTrue(inventory(self.folder)["ok"])
        for kwargs in ({"top": 0}, {"top": 1001}, {"max_file_bytes": -1}):
            with self.assertRaises(ValueError):
                inventory(self.folder, **kwargs)
        with self.assertRaises(ValueError):
            inventory(self.folder / "missing")
        self.assertEqual(mib("0.5"), 524288)
        for text in ("NaN", "Infinity", "-1", "wrong"):
            with self.assertRaises(Exception):
                mib(text)

    def test_report_new_path_only_and_output_omitted(self):
        output = self.folder / "report.json"
        save_report(inventory(self.folder), output)
        before = output.read_bytes()
        with self.assertRaises(FileExistsError):
            save_report({}, output)
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(inventory(self.folder, omit=[output])["files"], 0)
        self.assertEqual(list(self.folder.glob(".repolens-*")), [])

    def test_failed_report_encoding_creates_no_partial_output(self):
        output = self.folder / "report.json"
        with patch("repolens.json.dump", side_effect=ValueError("simulated failure")):
            with self.assertRaises(ValueError):
                save_report({}, output)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_cli_budget_json_export_and_invalid_folder(self):
        (self.folder / "main.py").write_text("print('example')\n")
        script = Path(__file__).resolve().parents[1] / "repolens.py"
        def run(*args):
            return subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True)
        output = self.folder / "report.json"
        result = run(self.folder, "--lines", "--json", "--output", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["files"], 1)
        self.assertEqual(json.loads(output.read_text())["line_statistics"]["total_lines"], 1)
        self.assertEqual(run(self.folder, "--max-file-mb", "0").returncode, 1)
        self.assertEqual(run(self.folder / "missing").returncode, 2)


if __name__ == "__main__":
    unittest.main()
