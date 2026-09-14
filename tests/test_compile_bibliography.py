from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compile_thuthesis_project  # noqa: E402


class CompileBibliographyIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.main = self.root / "thesis.tex"
        self.main.write_text(
            r"\documentclass{thuthesis}" + "\n" + r"\begin{document}Test\end{document}" + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def invoke(self, fake_run) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        argv = [
            "compile_thuthesis_project.py",
            str(self.root),
            "--main",
            "thesis.tex",
        ]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(
            compile_thuthesis_project, "find_executable", return_value="/usr/bin/true"
        ), mock.patch.object(
            compile_thuthesis_project, "run_command", side_effect=fake_run
        ), redirect_stdout(stdout):
            return_code = compile_thuthesis_project.main()
        return return_code, json.loads(stdout.getvalue())

    def successful_artifacts(self, z_only: bool = False):
        def fake_run(command, cwd, timeout):
            del command, timeout
            root = Path(cwd)
            (root / "thesis.pdf").write_bytes(b"%PDF-1.4\n")
            (root / "thesis.aux").write_text(
                r"\citation{alpha}" + "\n" + r"\bibdata{ref/refs}" + "\n",
                encoding="utf-8",
            )
            body = r"\newblock \allowbreak[Z]." if z_only else "Author.\\newblock Title[A]."
            (root / "thesis.bbl").write_text(
                "\\begin{thebibliography}{1}\n"
                "\\bibitem{alpha}\n"
                + body
                + "\n\\end{thebibliography}\n",
                encoding="utf-8",
            )
            (root / "thesis.blg").write_text("warning$ -- 0\n", encoding="utf-8")
            return {"command": ["latexmk"], "returncode": 0, "ok": True, "output_tail": ""}

        return fake_run

    def test_compile_success_includes_successful_artifact_audit(self) -> None:
        commands = []

        def fake_run(command, cwd, timeout):
            commands.append(command)
            return self.successful_artifacts()(command, cwd, timeout)

        return_code, result = self.invoke(fake_run)
        self.assertEqual(return_code, 0)
        self.assertTrue(result["compile_ok"])
        self.assertTrue(result["bibliography_artifacts"]["ok"])
        self.assertTrue(result["ok"])
        self.assertIn("pdf_path", result)
        self.assertTrue(result["artifact_freshness"]["pdf"])
        self.assertIn("-g", commands[0])

    def test_stale_pdf_cannot_satisfy_compile_validation(self) -> None:
        (self.root / "thesis.pdf").write_bytes(b"%PDF-1.4\nstale\n")

        def fake_run(command, cwd, timeout):
            del command, cwd, timeout
            return {"command": ["latexmk"], "returncode": 0, "ok": True, "output_tail": ""}

        return_code, result = self.invoke(fake_run)
        self.assertEqual(return_code, 1)
        self.assertFalse(result["compile_ok"])
        self.assertFalse(result["artifact_freshness"]["pdf"])
        self.assertIn("not refreshed", result["reason"])

    def test_fresh_pdf_cannot_mask_stale_aux(self) -> None:
        (self.root / "thesis.aux").write_text(r"\citation{old}" + "\n", encoding="utf-8")

        def fake_run(command, cwd, timeout):
            del command, timeout
            (Path(cwd) / "thesis.pdf").write_bytes(b"%PDF-1.4\nfresh\n")
            return {"command": ["latexmk"], "returncode": 0, "ok": True, "output_tail": ""}

        return_code, result = self.invoke(fake_run)
        self.assertEqual(return_code, 1)
        self.assertFalse(result["compile_ok"])
        self.assertTrue(result["artifact_freshness"]["pdf"])
        self.assertFalse(result["artifact_freshness"]["aux"])
        self.assertIn("AUX file was not refreshed", result["reason"])

    def test_fresh_aux_requires_fresh_bibliography_artifacts(self) -> None:
        (self.root / "thesis.bbl").write_text(
            "\\begin{thebibliography}{1}\n\\bibitem{old} Old.\n\\end{thebibliography}\n",
            encoding="utf-8",
        )
        (self.root / "thesis.blg").write_text("warning$ -- 0\n", encoding="utf-8")

        def fake_run(command, cwd, timeout):
            del command, timeout
            root = Path(cwd)
            (root / "thesis.pdf").write_bytes(b"%PDF-1.4\nfresh\n")
            (root / "thesis.aux").write_text(
                r"\citation{new}" + "\n" + r"\bibdata{ref/refs}" + "\n",
                encoding="utf-8",
            )
            return {"command": ["latexmk"], "returncode": 0, "ok": True, "output_tail": ""}

        return_code, result = self.invoke(fake_run)
        self.assertEqual(return_code, 1)
        self.assertFalse(result["compile_ok"])
        self.assertTrue(result["artifact_freshness"]["aux"])
        self.assertFalse(result["artifact_freshness"]["bbl"])
        self.assertFalse(result["artifact_freshness"]["blg"])
        self.assertIn("not refreshed: bbl, blg", result["reason"])

    def test_pdf_symlink_is_rejected_before_compile(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside.pdf"
        outside.write_bytes(b"outside")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        (self.root / "thesis.pdf").symlink_to(outside)

        called = False

        def fake_run(command, cwd, timeout):
            nonlocal called
            called = True
            return {"command": command, "returncode": 0, "ok": True, "output_tail": ""}

        return_code, result = self.invoke(fake_run)
        self.assertEqual(return_code, 2)
        self.assertFalse(result["ok"])
        self.assertFalse(called)
        self.assertIn("symbolic link", result["reason"])

    def test_option_like_main_name_is_rejected(self) -> None:
        option_like = self.root / "-CA.tex"
        option_like.write_text(self.main.read_text(encoding="utf-8"), encoding="utf-8")
        with self.assertRaises(compile_thuthesis_project.CompileInputError):
            compile_thuthesis_project.choose_main(self.root, "-CA.tex")

    def test_artifact_failure_does_not_erase_compile_success(self) -> None:
        return_code, result = self.invoke(self.successful_artifacts(z_only=True))
        self.assertEqual(return_code, 1)
        self.assertTrue(result["compile_ok"])
        self.assertFalse(result["bibliography_artifacts"]["ok"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "compile succeeded but the bibliography artifact audit failed")

    def test_compile_failure_marks_artifact_audit_skipped(self) -> None:
        def fake_run(command, cwd, timeout):
            del command, cwd, timeout
            return {"command": ["latexmk"], "returncode": 1, "ok": False, "output_tail": "failed"}

        return_code, result = self.invoke(fake_run)
        self.assertEqual(return_code, 1)
        self.assertFalse(result["compile_ok"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["bibliography_artifacts"]["skipped"])

    def test_compile_without_citations_does_not_require_bbl(self) -> None:
        def fake_run(command, cwd, timeout):
            del command, timeout
            root = Path(cwd)
            (root / "thesis.pdf").write_bytes(b"%PDF-1.4\n")
            (root / "thesis.aux").write_text(
                r"\relax" + "\n" + r"\bibdata{ref/refs}" + "\n",
                encoding="utf-8",
            )
            (root / "thesis.bbl").write_text("", encoding="utf-8")
            (root / "thesis.blg").write_text(
                "I found no \\citation commands\n(There was 1 error message)\n",
                encoding="utf-8",
            )
            return {"command": ["latexmk"], "returncode": 0, "ok": True, "output_tail": ""}

        return_code, result = self.invoke(fake_run)
        self.assertEqual(return_code, 0)
        self.assertTrue(result["ok"])
        self.assertFalse(result["bibliography_artifacts"]["bibliography_requested"])

    def test_compile_ignores_stale_bibliography_failures_without_current_citations(self) -> None:
        def fake_run(command, cwd, timeout):
            del command, timeout
            root = Path(cwd)
            (root / "thesis.pdf").write_bytes(b"%PDF-1.4\n")
            (root / "thesis.aux").write_text(r"\relax" + "\n", encoding="utf-8")
            (root / "thesis.bbl").write_text(
                "\\begin{thebibliography}{1}\n"
                "\\bibitem{old}\n\\newblock \\allowbreak[Z].\n"
                "\\end{thebibliography}\n",
                encoding="utf-8",
            )
            (root / "thesis.blg").write_text(
                "I couldn't open database file old.bib\n",
                encoding="utf-8",
            )
            return {"command": ["latexmk"], "returncode": 0, "ok": True, "output_tail": ""}

        return_code, result = self.invoke(fake_run)
        self.assertEqual(return_code, 0)
        self.assertTrue(result["compile_ok"])
        self.assertTrue(result["bibliography_artifacts"]["ok"])
        self.assertTrue(result["ok"])
        self.assertEqual(
            [warning["type"] for warning in result["bibliography_artifacts"]["warnings"]],
            ["stale_bibliography_artifact", "stale_bibliography_artifact"],
        )


if __name__ == "__main__":
    unittest.main()
