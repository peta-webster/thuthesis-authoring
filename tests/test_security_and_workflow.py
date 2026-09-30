from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_bibliography_consistency  # noqa: E402
import check_bibliography_preservation  # noqa: E402
import extract_source_document  # noqa: E402
import init_thuthesis_project  # noqa: E402
import merge_bibliography_entries  # noqa: E402
import run_quality_gates  # noqa: E402
from _subprocess_safety import run_captured  # noqa: E402
from _thuthesis_paths import classify  # noqa: E402


class PandocBoundaryTests(unittest.TestCase):
    def test_option_like_docx_name_is_terminated_and_absolutized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "--lua-filter=probe.docx"
            source.write_bytes(b"placeholder")
            completed = subprocess.CompletedProcess([], 0, "", "")
            with mock.patch.object(extract_source_document, "run_captured", return_value=completed) as runner:
                result = extract_source_document.parse_docx_pandoc_analysis(source, "/usr/bin/pandoc")

        self.assertEqual(result["blocks"], [])
        command = runner.call_args.args[0]
        self.assertEqual(command[-2], "--")
        self.assertEqual(command[-1], str(source.resolve()))
        self.assertTrue(Path(command[-1]).is_absolute())

    def test_force_stdlib_does_not_claim_pandoc_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.docx"
            source.write_bytes(b"placeholder")
            argv = ["extract_source_document.py", "--force-stdlib", str(source)]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                extract_source_document, "find_pandoc", return_value="/usr/bin/pandoc"
            ), mock.patch.object(
                extract_source_document,
                "parse_docx_stdlib",
                return_value=([{"type": "paragraph", "text": "body"}], [], []),
            ), redirect_stdout(stdout):
                return_code = extract_source_document.main()
            result = json.loads(stdout.getvalue())

        self.assertEqual(return_code, 0)
        self.assertTrue(result["pandoc_available"])
        self.assertIn("--force-stdlib", result["warnings"][0])
        self.assertNotIn("未找到 pandoc", result["warnings"][0])


class ProcessLifetimeTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "process-group termination is POSIX-specific")
    def test_timeout_kills_descendant_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "descendant-finished"
            child = (
                "import pathlib,time; "
                "time.sleep(0.5); "
                f"pathlib.Path({str(marker)!r}).write_text('late')"
            )
            parent = (
                "import subprocess,sys,time; "
                f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
                "time.sleep(5)"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                run_captured([sys.executable, "-c", parent], timeout=0.1)
            time.sleep(0.7)
            self.assertFalse(marker.exists())


class InitializationBoundaryTests(unittest.TestCase):
    EXAMPLE = r"""\documentclass{thuthesis}
\input{thusetup}
\begin{document}
\maketitle
\input{data/committee}
\frontmatter
\input{data/abstract}
\tableofcontents
\input{data/denotation}
\mainmatter
\input{data/chap01}
\input{data/chap02}
\bibliography{ref/refs}
\appendix
\input{data/appendix}
\backmatter
\input{data/acknowledgements}
\input{data/resume}
\input{data/comments}
\input{data/resolution}
\end{document}
"""

    def make_release(self, root: Path, chapters: list[str]) -> None:
        (root / "data").mkdir(parents=True)
        (root / "ref").mkdir()
        files = {
            "LICENSE": "LPPL\n",
            "thuthesis.cls": "class\n",
            "thuthesis-example.tex": self.EXAMPLE,
            "thuthesis-example.pdf": "example pdf\n",
            "thuthesis.pdf": "manual pdf\n",
            "thusetup.tex": "% !TEX root = ./thuthesis-example.tex\n",
            "ref/refs.bib": "@misc{example, title={Example}}\n",
            "data/abstract.tex": "% !TEX root = ../thuthesis-example.tex\n",
            "data/committee.tex": "\\begin{committee}\nCommittee.\n\\end{committee}\n",
            "data/denotation.tex": "\\begin{denotation}\nSymbols.\n\\end{denotation}\n",
            "data/appendix.tex": "\\chapter{Appendix}\nAppendix.\n",
            "data/acknowledgements.tex": (
                "\\begin{acknowledgements}\nThanks.\n\\end{acknowledgements}\n"
            ),
            "data/resume.tex": "\\begin{resume}\nResume.\n\\end{resume}\n",
            "data/comments.tex": (
                "% !TEX root = ../thuthesis-example.tex\n"
                "\\begin{comments}\nComments.\n\\end{comments}\n"
            ),
            "data/resolution.tex": "\\begin{resolution}\nResolution.\n\\end{resolution}\n",
        }
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        for relative in chapters:
            (root / relative).write_text(
                "% !TEX root = ../thuthesis-example.tex\n\\chapter{Generated}\n",
                encoding="utf-8",
            )

    def test_copies_example_and_assembles_planned_mapping(self) -> None:
        chapters = ["data/methods.tex", "data/results.tex"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "release"
            destination = root / "thesis"
            self.make_release(source, ["data/chap01.tex"])
            example_hash = init_thuthesis_project.sha256_file(source / "thuthesis-example.tex")
            page_hashes = {
                relative: init_thuthesis_project.sha256_file(source / relative)
                for relative in init_thuthesis_project.PAGE_ANNOTATIONS
            }

            result = init_thuthesis_project.copy_release(source, destination, "main.tex", chapters)
            main_text = (destination / "main.tex").read_text(encoding="utf-8")

            self.assertEqual(result["chapter_files"], chapters)
            self.assertEqual(result["created_chapter_files"], chapters)
            self.assertEqual(init_thuthesis_project.sha256_file(source / "thuthesis-example.tex"), example_hash)
            self.assertEqual(init_thuthesis_project.sha256_file(destination / "thuthesis-example.tex"), example_hash)
            self.assertEqual(main_text.count("[TODO:"), 11)
            self.assertEqual(main_text.count(init_thuthesis_project.METADATA_OVERLAY_BEGIN), 1)
            self.assertLess(main_text.index("\\input{thusetup}"), main_text.index("\\thusetup{"))
            self.assertIn("associate-supervisor  = {},", main_text)
            self.assertIn("associate-supervisor* = {},", main_text)
            self.assertIn("\\maketitle", main_text)
            self.assertIn("\\bibliography{ref/refs}", main_text)
            self.assertIn("\\appendix", main_text)
            self.assertIn("\\backmatter", main_text)
            self.assertNotIn("data/chap01", main_text)
            self.assertLess(main_text.index("data/methods"), main_text.index("data/results"))
            self.assertIn("../main.tex", (destination / "data/methods.tex").read_text(encoding="utf-8"))
            self.assertEqual(result["root_directive_files"], chapters)
            self.assertEqual(result["metadata_todo_fields"], list(init_thuthesis_project.METADATA_TODO_FIELDS))
            self.assertEqual(result["cleared_template_fields"], list(init_thuthesis_project.CLEARED_TEMPLATE_FIELDS))
            self.assertEqual(result["generated_todo_count"], 18)
            self.assertEqual(len(result["annotated_optional_files"]), 3)
            self.assertEqual(len(result["annotated_sensitive_files"]), 4)
            for relative, before_hash in page_hashes.items():
                self.assertEqual(init_thuthesis_project.sha256_file(source / relative), before_hash)
                copied = (destination / relative).read_text(encoding="utf-8")
                self.assertEqual(copied.count("[TODO:"), 1)
                if relative in result["annotated_sensitive_files"]:
                    self.assertIn("BLOCKING:", copied)
                    self.assertIn("禁止直接提交", copied)
                else:
                    self.assertNotIn("BLOCKING:", copied)
            self.assertIn(
                "./thuthesis-example.tex",
                (destination / "thusetup.tex").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "../thuthesis-example.tex",
                (destination / "data/comments.tex").read_text(encoding="utf-8"),
            )

    def test_page_annotation_failure_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "release"
            destination = root / "thesis"
            self.make_release(source, ["data/chap01.tex"])
            (source / "data/resolution.tex").write_text("No resolution environment.\n", encoding="utf-8")

            with self.assertRaises(init_thuthesis_project.InitializationError):
                init_thuthesis_project.copy_release(source, destination)

            self.assertFalse(destination.exists())

    def test_metadata_or_page_anchor_ambiguity_is_rejected(self) -> None:
        with self.assertRaises(init_thuthesis_project.InitializationError):
            init_thuthesis_project.add_metadata_overlay("\\input{thusetup}\n\\input{thusetup}\n")
        with self.assertRaises(init_thuthesis_project.InitializationError):
            init_thuthesis_project.annotate_example_page(
                "\\begin{comments}\n\\end{comments}\n\\begin{comments}\n\\end{comments}\n",
                "comments",
                True,
                "data/comments.tex",
            )

    def test_discovers_existing_chapters_in_natural_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "release"
            destination = root / "thesis"
            self.make_release(source, ["data/chap10.tex", "data/chap2.tex"])

            result = init_thuthesis_project.copy_release(source, destination)

        self.assertEqual(result["chapter_files"], ["data/chap2.tex", "data/chap10.tex"])

    def test_rejects_unsafe_chapter_existing_user_main_and_bad_main_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "release"
            self.make_release(source, ["data/chap01.tex"])
            with self.assertRaises(init_thuthesis_project.InitializationError):
                init_thuthesis_project.normalize_chapters(["data/comments.tex"])
            with self.assertRaises(init_thuthesis_project.InitializationError):
                init_thuthesis_project.copy_release(
                    source,
                    root / "unsafe-chapter",
                    "main.tex",
                    ["../outside.tex"],
                )
            with self.assertRaises(init_thuthesis_project.InitializationError):
                init_thuthesis_project.normalize_user_main("main\nUnexpectedText.tex")
            (source / "main.tex").write_text("existing\n", encoding="utf-8")
            with self.assertRaises(init_thuthesis_project.InitializationError):
                init_thuthesis_project.copy_release(source, root / "existing-main", "main.tex")

    def test_redirect_handler_rejects_http_and_unapproved_hosts_before_following(self) -> None:
        handler = init_thuthesis_project.SafeRedirectHandler()
        request = urllib.request.Request("https://github.com/tuna/thuthesis/releases/download/v7.7.1/x.zip")
        for target in ("http://github.com/file.zip", "https://example.com/file.zip"):
            with self.subTest(target=target), self.assertRaises(init_thuthesis_project.InitializationError):
                handler.redirect_request(request, None, 302, "Found", {}, target)

    def test_zip_rejects_casefold_duplicate_and_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / "duplicate.zip"
            with zipfile.ZipFile(duplicate, "w") as archive:
                archive.writestr("Data/File.tex", "a")
                archive.writestr("data/file.tex", "b")
            with self.assertRaises(init_thuthesis_project.InitializationError):
                init_thuthesis_project.extract_zip_safely(duplicate, root / "duplicate-out")

            traversal = root / "traversal.zip"
            with zipfile.ZipFile(traversal, "w") as archive:
                archive.writestr("../escape", "bad")
            with self.assertRaises(init_thuthesis_project.InitializationError):
                init_thuthesis_project.extract_zip_safely(traversal, root / "traversal-out")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO test requires POSIX")
    def test_local_release_tree_rejects_special_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.mkfifo(root / "unexpected-pipe")
            with self.assertRaises(init_thuthesis_project.InitializationError):
                init_thuthesis_project.validate_release_tree(root)

class TargetAndBibliographyTests(unittest.TestCase):
    def test_invalid_target_short_circuits_without_reading_external_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "project"
            baseline = workspace / "baseline"
            (root / "data").mkdir(parents=True)
            baseline.mkdir()
            outside = workspace / "outside.tex"
            sentinel = "[TODO: EXTERNAL_SECRET_SENTINEL]"
            outside.write_text(sentinel + "\n", encoding="utf-8")
            argv = [
                "run_quality_gates.py",
                str(root),
                str(outside),
                "--baseline-root",
                str(baseline),
                "--skip-bibliography",
            ]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv), redirect_stdout(stdout):
                return_code = run_quality_gates.main()
            output = stdout.getvalue()
            result = json.loads(output)

        self.assertEqual(return_code, 1)
        self.assertNotIn(sentinel, output)
        self.assertFalse(result["gates"]["target_validation"]["ok"])
        self.assertTrue(result["gates"]["latex_safety"]["skipped"])
        self.assertTrue(result["gates"]["todo_and_claims"]["skipped"])

    def test_skip_tex_preservation_still_requires_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "ref").mkdir()
            (root / "data" / "new.tex").write_text("New text.\n", encoding="utf-8")
            (root / "ref" / "refs.bib").write_text(
                "@misc{old, title={{Old}}}\n",
                encoding="utf-8",
            )
            argv = [
                "run_quality_gates.py",
                str(root),
                "data/new.tex",
                "--skip-preservation",
                "--preservation-skip-reason",
                "new target confirmed by user",
                "--source-backed",
            ]
            with mock.patch.object(sys, "argv", argv), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    run_quality_gates.main()
        self.assertEqual(raised.exception.code, 2)

    def test_target_validation_rejects_symlink_alias_and_accepts_declared_bib(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "data").mkdir()
            (root / "ref").mkdir()
            (root / "data" / "real.tex").write_text("text", encoding="utf-8")
            (root / "data" / "alias.tex").symlink_to(root / "data" / "real.tex")
            (root / "ref" / "refs.bib").write_text("", encoding="utf-8")

            alias = classify(root, "data/alias.tex")
            bibliography = classify(root, "ref/refs.bib", allow_bibliography=True)

        self.assertFalse(alias["ok"])
        self.assertIn("symbolic links", alias["reason"])
        self.assertTrue(bibliography["ok"])

    def test_merge_is_append_only_and_rejects_existing_key(self) -> None:
        existing = "@misc{old, title={{Old}}}\n"
        addition = "@misc{new, title={{New}}}\n"
        merged, result = merge_bibliography_entries.merge_text(existing, addition)
        self.assertTrue(result["ok"])
        self.assertTrue(merged.startswith(existing))
        self.assertEqual(result["new_keys"], ["new"])

        unchanged, collision = merge_bibliography_entries.merge_text(existing, "@misc{old, title={{Other}}}")
        self.assertFalse(collision["ok"])
        self.assertEqual(unchanged, existing)

        unchanged, directive = merge_bibliography_entries.merge_text(
            existing,
            "@preamble{\\input{unexpected}}\n@misc{new, title={{New}}}",
        )
        self.assertFalse(directive["ok"])
        self.assertEqual(unchanged, existing)

    def test_bibliography_preservation_detects_existing_content_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "before.bib"
            current = root / "after.bib"
            baseline.write_text("@misc{old, title={{Old}}}\n", encoding="utf-8")
            current.write_text("@misc{old, title={{Changed}}}\n", encoding="utf-8")
            result = check_bibliography_preservation.check_files(baseline, current)
        self.assertFalse(result["ok"])
        self.assertIn("existing_bibliography_content_changed", {item["type"] for item in result["issues"]})

    def test_bibliography_preservation_rejects_directives_and_unparsed_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "before.bib"
            current = root / "after.bib"
            old = "@misc{old, title={{Old}}}\n"
            baseline.write_text(old, encoding="utf-8")
            for suffix in (
                '@preamble{"\\\\input{unexpected}"}\n',
                "unexpected prose\n@misc{new, title={{New}}}\n",
            ):
                with self.subTest(suffix=suffix):
                    current.write_text(old + suffix, encoding="utf-8")
                    result = check_bibliography_preservation.check_files(baseline, current)
                    self.assertFalse(result["ok"])
                    self.assertIn(
                        "invalid_appended_bibliography_content",
                        {item["type"] for item in result["issues"]},
                    )

    def test_quality_gate_passes_append_only_bibliography_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "project"
            baseline = workspace / "baseline"
            for base in (root, baseline):
                (base / "data").mkdir(parents=True)
                (base / "ref").mkdir()
            (baseline / "data" / "chap01.tex").write_text("Background.\n", encoding="utf-8")
            (root / "data" / "chap01.tex").write_text(r"Background \cite{new}." + "\n", encoding="utf-8")
            old = "@misc{old, title={{Old}}}\n"
            (baseline / "ref" / "refs.bib").write_text(old, encoding="utf-8")
            (root / "ref" / "refs.bib").write_text(
                old + "\n@misc{new, title={{New reference}}}\n",
                encoding="utf-8",
            )
            argv = [
                "run_quality_gates.py",
                str(root),
                "data/chap01.tex",
                "--baseline-root",
                str(baseline),
                "--bibliography-targets",
                "ref/refs.bib",
                "--source-backed",
            ]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv), redirect_stdout(stdout):
                return_code = run_quality_gates.main()
            result = json.loads(stdout.getvalue())

        self.assertEqual(return_code, 0)
        self.assertTrue(result["ok"])
        self.assertTrue(result["gates"]["bibliography_preservation"]["ok"])

    def test_quality_gate_rejects_undeclared_bibliography_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "project"
            baseline = workspace / "baseline"
            for base in (root, baseline):
                (base / "data").mkdir(parents=True)
                (base / "ref").mkdir()
                (base / "data" / "chap01.tex").write_text("Background.\n", encoding="utf-8")
            (baseline / "ref" / "refs.bib").write_text(
                "@misc{old, title={{Old}}}\n",
                encoding="utf-8",
            )
            (root / "ref" / "refs.bib").write_text(
                "@misc{old, title={{Changed}}}\n",
                encoding="utf-8",
            )
            argv = [
                "run_quality_gates.py",
                str(root),
                "data/chap01.tex",
                "--baseline-root",
                str(baseline),
                "--source-backed",
            ]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv), redirect_stdout(stdout):
                return_code = run_quality_gates.main()
            result = json.loads(stdout.getvalue())

        self.assertEqual(return_code, 1)
        preservation = result["gates"]["bibliography_preservation"]
        self.assertFalse(preservation["ok"])
        self.assertEqual(
            preservation["change_declaration_audit"]["undeclared_paths"],
            ["ref/refs.bib"],
        )

    def test_new_tex_skip_does_not_skip_existing_bibliography_preservation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "project"
            baseline = workspace / "baseline"
            (root / "data").mkdir(parents=True)
            (root / "ref").mkdir()
            (baseline / "ref").mkdir(parents=True)
            (root / "data" / "new.tex").write_text(r"New text \cite{new}." + "\n", encoding="utf-8")
            old = "@misc{old, title={{Old}}}\n"
            (baseline / "ref" / "refs.bib").write_text(old, encoding="utf-8")
            (root / "ref" / "refs.bib").write_text(
                old + "\n@misc{new, title={{New}}}\n",
                encoding="utf-8",
            )
            argv = [
                "run_quality_gates.py",
                str(root),
                "data/new.tex",
                "--baseline-root",
                str(baseline),
                "--skip-preservation",
                "--preservation-skip-reason",
                "new target confirmed by user",
                "--bibliography-targets",
                "ref/refs.bib",
                "--source-backed",
            ]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv), redirect_stdout(stdout):
                return_code = run_quality_gates.main()
            result = json.loads(stdout.getvalue())

        self.assertEqual(return_code, 0)
        self.assertTrue(result["gates"]["preservation"]["skipped"])
        self.assertFalse(result["gates"]["bibliography_preservation"].get("skipped", False))
        self.assertTrue(result["gates"]["bibliography_preservation"]["ok"])

    def test_citations_inside_literal_environment_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            chapter = root / "data" / "chap.tex"
            chapter.write_text("\\begin{verbatim}\\cite{fake}\\end{verbatim}\n", encoding="utf-8")
            result = check_bibliography_consistency.check_project(root, [chapter], [])
        self.assertTrue(result["ok"])
        self.assertEqual(result["citation_keys"], [])


class MainTodoStatusTests(unittest.TestCase):
    def test_unbraced_or_dynamic_inputs_make_audit_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "data").mkdir()
            (root / "data/chapter.tex").write_text("[TODO: missing evidence]\n", encoding="utf-8")
            for statement in (
                r"\input data/chapter",
                r"\include data/chapter",
                r"\input\chapterfile",
                r"\input{data/\chapterfile}",
                r"\input{data/chapter",
            ):
                with self.subTest(statement=statement):
                    (root / "main.tex").write_text("Complete.\n" + statement + "\n", encoding="utf-8")
                    ready, status = run_quality_gates.audit_main_todos(root, "main.tex")
                    self.assertFalse(ready)
                    self.assertFalse(status["audit_complete"])
                    self.assertIn("dynamic_or_unsupported_input", {issue["type"] for issue in status["issues"]})

    def test_input_lookalikes_and_literal_commands_do_not_block_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "chapter.tex").write_text("Complete.\n", encoding="utf-8")
            (root / "main.tex").write_text(
                "% \\input ignored\n"
                "\\verb|\\input ignored|\n"
                "\\begin{verbatim}\\input ignored\\end{verbatim}\n"
                "\\includegraphics{plot}\n\\inputencoding{utf8}\n"
                "\\input {chapter}\n",
                encoding="utf-8",
            )
            ready, status = run_quality_gates.audit_main_todos(root, "main.tex")
        self.assertTrue(ready)
        self.assertTrue(status["audit_complete"])
        self.assertEqual(status["reachable_files"], ["chapter.tex", "main.tex"])

    def test_quality_gate_reports_unbraced_input_without_changing_structural_ok(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "project"
            baseline = workspace / "baseline"
            for base in (root, baseline):
                (base / "data").mkdir(parents=True)
                (base / "data/chapter.tex").write_text("[TODO: fill chapter]\n", encoding="utf-8")
            (root / "main.tex").write_text("\\input data/chapter\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_quality_gates.py"), str(root), "data/chapter.tex",
                 "--baseline-root", str(baseline), "--skip-bibliography", "--main", "main.tex"],
                capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertFalse(report["submission_ready"])
        self.assertFalse(report["main_todo_status"]["audit_complete"])

    def test_main_graph_counts_active_commented_and_blocking_todos(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "data").mkdir()
            (root / "thusetup.tex").write_text("Setup.\n", encoding="utf-8")
            (root / "main.tex").write_text(
                "\\input{thusetup}\n"
                "[TODO: active metadata]\n"
                "% [TODO: commented reminder]\n"
                "\\input{data/chapter}\n"
                "% \\input{data/skipped}\n",
                encoding="utf-8",
            )
            (root / "data/chapter.tex").write_text(
                "[TODO: BLOCKING: replace process page]\n\\input{part}\n",
                encoding="utf-8",
            )
            (root / "data/part.tex").write_text("Complete.\n", encoding="utf-8")

            ready, status = run_quality_gates.audit_main_todos(root, "main.tex")

        self.assertFalse(ready)
        self.assertTrue(status["audit_complete"])
        self.assertEqual(status["todo_count"], 3)
        self.assertEqual(status["active_todo_count"], 2)
        self.assertEqual(status["commented_todo_count"], 1)
        self.assertEqual(status["blocking_todo_count"], 1)
        self.assertEqual(
            status["reachable_files"],
            ["data/chapter.tex", "data/part.tex", "main.tex", "thusetup.tex"],
        )

    def test_incomplete_graph_is_not_submission_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "main.tex").write_text("\\input{data/missing}\n", encoding="utf-8")
            ready, status = run_quality_gates.audit_main_todos(root, "main.tex")
        self.assertFalse(ready)
        self.assertFalse(status["audit_complete"])
        self.assertIn("missing_input", {issue["type"] for issue in status["issues"]})

    def test_quality_gate_reports_readiness_without_changing_ok(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "project"
            baseline = workspace / "baseline"
            for base in (root, baseline):
                (base / "data").mkdir(parents=True)
                (base / "ref").mkdir()
                (base / "data/chapter.tex").write_text("[TODO: fill chapter]\n", encoding="utf-8")
            (root / "main.tex").write_text("\\input{data/chapter}\n", encoding="utf-8")
            argv = [
                "run_quality_gates.py",
                str(root),
                "data/chapter.tex",
                "--baseline-root",
                str(baseline),
                "--skip-bibliography",
                "--main",
                "main.tex",
            ]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv), redirect_stdout(stdout):
                return_code = run_quality_gates.main()
            result = json.loads(stdout.getvalue())

            (root / "data/chapter.tex").write_text("Complete.\n", encoding="utf-8")
            ready, status = run_quality_gates.audit_main_todos(root, "main.tex")

        self.assertEqual(return_code, 0)
        self.assertTrue(result["ok"])
        self.assertFalse(result["submission_ready"])
        self.assertEqual(result["main_todo_status"]["todo_count"], 1)
        self.assertTrue(ready)
        self.assertEqual(status["todo_count"], 0)

    def test_quality_gate_without_main_keeps_legacy_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "project"
            baseline = workspace / "baseline"
            for base in (root, baseline):
                (base / "data").mkdir(parents=True)
                (base / "ref").mkdir()
                (base / "data/chapter.tex").write_text("Complete.\n", encoding="utf-8")
            argv = [
                "run_quality_gates.py",
                str(root),
                "data/chapter.tex",
                "--baseline-root",
                str(baseline),
                "--skip-bibliography",
            ]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv), redirect_stdout(stdout):
                return_code = run_quality_gates.main()
            result = json.loads(stdout.getvalue())

        self.assertEqual(return_code, 0)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["submission_ready"])
        self.assertTrue(result["main_todo_status"]["audit_skipped"])


if __name__ == "__main__":
    unittest.main()
