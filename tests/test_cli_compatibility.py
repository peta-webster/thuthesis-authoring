from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class CliCompatibilityTests(unittest.TestCase):
    TABLE = "| A | B |\n| --- | ---: |\n| 1 | 2 |\n"

    def run_script(
        self,
        script: str,
        *arguments: object,
        input_text: Optional[str] = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), *(str(arg) for arg in arguments)],
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )

    def parse_json(self, completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"stdout is not JSON: {exc}\nstdout={completed.stdout!r}\nstderr={completed.stderr!r}")
        self.assertIsInstance(result, dict)
        return result

    def assert_top_level_fields(self, result: dict[str, object], *fields: str) -> None:
        for field in fields:
            with self.subTest(field=field):
                self.assertIn(field, result)

    def test_extractor_success_preserves_legacy_json_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.md"
            source.write_text("# Heading\n\nBody [1].\n", encoding="utf-8")
            completed = self.run_script("extract_source_document.py", source)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = self.parse_json(completed)
        self.assertTrue(result["ok"])
        self.assert_top_level_fields(
            result,
            "ok",
            "source",
            "format",
            "extractor",
            "pandoc_available",
            "heading_count",
            "block_count",
            "headings",
            "blocks",
            "numeric_citation_markers",
            "manual_review",
            "warnings",
        )

    def test_extractor_unsupported_format_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.pdf"
            source.write_bytes(b"not a source document")
            completed = self.run_script("extract_source_document.py", source)

        self.assertEqual(completed.returncode, 2, completed.stderr)
        result = self.parse_json(completed)
        self.assertFalse(result["ok"])
        self.assert_top_level_fields(result, "ok", "error", "supported")
        self.assertIn("unsupported source format", str(result["error"]))

    def test_escape_text_cli_keeps_plain_mode(self) -> None:
        completed = self.run_script("escape_latex_text.py", "--text", "a_b% & $x$")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, r"a\_b\% \& \$x\$" + "\n")

    def test_escape_math_aware_cli_preserves_balanced_math(self) -> None:
        completed = self.run_script(
            "escape_latex_text.py",
            "--math-aware",
            "--text",
            "$x_1$ & a_b%",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "$x_1$ \\& a\\_b\\%\n")

    def test_table_cli_accepts_stdin_and_text(self) -> None:
        stdin_result = self.run_script(
            "convert_markdown_tables.py",
            "--label-prefix",
            "stdin",
            input_text=self.TABLE,
        )
        text_result = self.run_script(
            "convert_markdown_tables.py",
            "--label-prefix",
            "inline",
            "--text",
            self.TABLE,
        )

        self.assertEqual(stdin_result.returncode, 0, stdin_result.stderr)
        self.assertIn(r"\label{tab:stdin1}", stdin_result.stdout)
        self.assertEqual(text_result.returncode, 0, text_result.stderr)
        self.assertIn(r"\label{tab:inline1}", text_result.stdout)

    def test_table_file_mode_is_a_json_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chapter = Path(directory) / "chapter.md"
            chapter.write_text(self.TABLE, encoding="utf-8")
            completed = self.run_script("convert_markdown_tables.py", chapter)
            after = chapter.read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = self.parse_json(completed)
        self.assert_top_level_fields(result, "ok", "results")
        self.assertTrue(result["ok"])
        self.assertEqual(after, self.TABLE)
        self.assertEqual(result["results"], [{
            "file": str(chapter),
            "tables_converted": 1,
            "changed": True,
        }])

    def test_table_in_place_continues_labels_across_multiple_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.md"
            second = Path(directory) / "second.md"
            first.write_text(self.TABLE, encoding="utf-8")
            second.write_text(self.TABLE, encoding="utf-8")
            completed = self.run_script(
                "convert_markdown_tables.py",
                "--in-place",
                "--label-prefix",
                "chapter",
                first,
                second,
            )
            first_after = first.read_text(encoding="utf-8")
            second_after = second.read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = self.parse_json(completed)
        self.assert_top_level_fields(result, "ok", "results")
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["results"]), 2)
        self.assertTrue(all(item["changed"] for item in result["results"]))
        self.assertIn(r"\label{tab:chapter1}", first_after)
        self.assertIn(r"\label{tab:chapter2}", second_after)

    def test_static_bibliography_cli_success_preserves_legacy_json_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "ref").mkdir()
            (root / "data" / "chapter.tex").write_text(
                r"Text \cite{entry}." + "\n",
                encoding="utf-8",
            )
            (root / "ref" / "refs.bib").write_text(
                "@article{entry, author={A}, title={T}, year={2025}}\n",
                encoding="utf-8",
            )
            completed = self.run_script("check_bibliography_consistency.py", root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = self.parse_json(completed)
        self.assertTrue(result["ok"])
        self.assert_top_level_fields(
            result,
            "project_root",
            "ok",
            "tex_files",
            "bib_files",
            "citation_count",
            "citation_keys",
            "bib_key_count",
            "issues",
            "warnings",
        )

    def test_static_bibliography_cli_note_only_entry_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "ref").mkdir()
            (root / "data" / "chapter.tex").write_text(
                r"Text \cite{entry}." + "\n",
                encoding="utf-8",
            )
            (root / "ref" / "refs.bib").write_text(
                "@misc{entry, note={Hidden reference}}\n",
                encoding="utf-8",
            )
            completed = self.run_script("check_bibliography_consistency.py", root)

        self.assertEqual(completed.returncode, 1, completed.stderr)
        result = self.parse_json(completed)
        self.assert_top_level_fields(result, "project_root", "ok", "issues", "warnings")
        self.assertFalse(result["ok"])
        self.assertIn("note_only_cited_entry", {item["type"] for item in result["issues"]})

    def test_static_bibliography_cli_invalid_root_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            completed = self.run_script("check_bibliography_consistency.py", missing)

        self.assertEqual(completed.returncode, 2, completed.stderr)
        result = self.parse_json(completed)
        self.assert_top_level_fields(result, "project_root", "ok", "issues")
        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"][0]["type"], "invalid_project_root")

    def write_artifacts(self, root: Path, body: str) -> None:
        (root / "thesis.tex").write_text("", encoding="utf-8")
        (root / "thesis.aux").write_text(
            r"\citation{entry}" + "\n" + r"\bibdata{ref/refs}" + "\n",
            encoding="utf-8",
        )
        (root / "thesis.bbl").write_text(
            "\\begin{thebibliography}{1}\n"
            "\\bibitem{entry}\n"
            f"{body}\n"
            "\\end{thebibliography}\n",
            encoding="utf-8",
        )
        (root / "thesis.blg").write_text("warning$ -- 0\n", encoding="utf-8")

    def test_artifact_checker_cli_success_preserves_legacy_json_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_artifacts(root, r"Author.\newblock Title[A].")
            completed = self.run_script(
                "check_bibliography_artifacts.py",
                root,
                "--main",
                "thesis.tex",
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = self.parse_json(completed)
        self.assertTrue(result["ok"])
        self.assert_top_level_fields(
            result,
            "ok",
            "project_root",
            "main_file",
            "citation_keys",
            "citation_wildcard",
            "bibliography_requested",
            "aux",
            "bbl",
            "blg",
            "issues",
            "warnings",
        )

    def test_artifact_checker_cli_z_only_entry_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_artifacts(root, r"\newblock \allowbreak[Z].")
            completed = self.run_script(
                "check_bibliography_artifacts.py",
                root,
                "--main",
                "thesis.tex",
            )

        self.assertEqual(completed.returncode, 1, completed.stderr)
        result = self.parse_json(completed)
        self.assert_top_level_fields(result, "ok", "project_root", "main_file", "issues", "warnings")
        self.assertFalse(result["ok"])
        self.assertIn("z_only_bibitem", {item["type"] for item in result["issues"]})

    def test_artifact_checker_cli_invalid_root_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            completed = self.run_script(
                "check_bibliography_artifacts.py",
                missing,
                "--main",
                "thesis.tex",
            )

        self.assertEqual(completed.returncode, 2, completed.stderr)
        result = self.parse_json(completed)
        self.assert_top_level_fields(result, "ok", "project_root", "issues")
        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"][0]["type"], "invalid_project_root")


if __name__ == "__main__":
    unittest.main()
