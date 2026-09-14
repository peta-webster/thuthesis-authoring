"""Local example input and failure checks; no network or TeX required."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_example", ROOT / "tools/run_example.py")
example = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(example)


class ExampleTests(unittest.TestCase):
    def invoke(self, *args):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = example.main(list(map(str, args)))
        return code, json.loads(stdout.getvalue())

    def test_original_materials_and_calculation(self):
        result = example.validate_materials()
        self.assertEqual(result, {"count": 3, "sum": 12, "mean": 4})
        self.assertEqual(len(example.TODOS), 2)

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / "keep.txt"
            marker.write_text("user content")
            code, result = self.invoke("--output", root)
            self.assertEqual(code, 1)
            self.assertIn("already exists", result["error"])
            self.assertEqual(marker.read_text(), "user content")
            self.assertFalse((root / "result.json").exists())

    def test_dangling_output_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "output"
            output.symlink_to(root / "missing")
            code, result = self.invoke("--output", output)
            self.assertEqual(code, 1)
            self.assertIn("already exists", result["error"])
            self.assertTrue(output.is_symlink())
            self.assertFalse((root / "missing").exists())

    def test_wrong_archive_fails_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "wrong.zip"
            archive.write_bytes(b"not the pinned release")
            with mock.patch.object(example, "require_tools", side_effect=AssertionError("must verify archive first")):
                code, result = self.invoke("--output", root / "output", "--source", archive)
            self.assertEqual(code, 1)
            self.assertIn("SHA-256", result["error"])
            self.assertFalse((root / "output").exists())

    def test_missing_tex_never_becomes_success_or_starts_download(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            with mock.patch.object(example.compiler, "find_executable", return_value=None), mock.patch.object(
                example.initializer, "download_release", side_effect=AssertionError("must preflight tools first")
            ):
                code, result = self.invoke("--output", output)
            self.assertEqual(code, 1)
            self.assertFalse(result["ok"])
            self.assertIn("Missing TeX tools", result["error"])
            self.assertFalse(output.exists())

    def test_template_or_sensitive_page_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data").mkdir()
            paths = [root / "thuthesis.cls", root / "data/committee.tex"]
            for path in paths:
                path.write_text("original")
            before = {p.relative_to(root).as_posix(): example.digest(p) for p in paths}
            for path in paths:
                path.write_text("unexpected edit")
                with self.assertRaises(example.ExampleError):
                    example.check_preserved(root, before, "cited")
                path.write_text("original")


if __name__ == "__main__":
    unittest.main()
