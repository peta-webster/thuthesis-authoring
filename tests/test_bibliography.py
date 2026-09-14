from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_bibliography_artifacts  # noqa: E402
import check_bibliography_consistency  # noqa: E402
from _bibtex_parser import parse_bibtex  # noqa: E402


class BibTeXParserTests(unittest.TestCase):
    def test_nested_braces_quotes_parentheses_and_concatenation(self) -> None:
        text = r'''
@string{suffix = "Press"}
@article{nested,
  author = "Doe, {Jane}",
  title = {{Outer {Inner}} and \"Quoted\"},
  year = 20 # 24,
  note = {An ordinary {note}},
}
@misc(online,
  organization = {Example Org},
  title = "A {Web} Page",
  date = {2026-01-02},
  url = {https://example.test/a?x={y}},
)
'''
        entries, errors = parse_bibtex(text)
        self.assertEqual(errors, [])
        self.assertEqual([entry.key for entry in entries], ["nested", "online"])
        self.assertEqual(entries[0].fields["year"], "2024")
        self.assertIn("{Inner}", entries[0].fields["title"])
        self.assertEqual(entries[1].fields["organization"], "Example Org")

    def test_syntax_error_has_source_location(self) -> None:
        entries, errors = parse_bibtex("@misc{broken, title={never closes}\n", "bad.bib")
        self.assertEqual(entries, [])
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["line"], 2)
        self.assertGreaterEqual(errors[0]["column"], 1)


class StaticBibliographyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "data").mkdir()
        (self.root / "ref").mkdir()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def check(
        self,
        bib_text: str,
        cite_key: str = "entry",
        tex_text: Optional[str] = None,
    ) -> dict[str, object]:
        tex = self.root / "data" / "chapter.tex"
        bib = self.root / "ref" / "refs.bib"
        tex.write_text(
            tex_text if tex_text is not None else r"Text \cite{" + cite_key + "}.\n",
            encoding="utf-8",
        )
        bib.write_text(bib_text, encoding="utf-8")
        return check_bibliography_consistency.check_project(self.root, [tex], [bib])

    def test_note_only_cited_entry_fails(self) -> None:
        result = self.check("@misc{entry, note={Complete reference copied into note}}\n")
        self.assertFalse(result["ok"])
        self.assertIn("note_only_cited_entry", {issue["type"] for issue in result["issues"]})

    def test_non_renderable_cited_entry_fails(self) -> None:
        result = self.check("@misc{entry, keywords={ai, economics}}\n")
        self.assertFalse(result["ok"])
        self.assertIn("non_renderable_cited_entry", {issue["type"] for issue in result["issues"]})

    def test_structured_entry_with_ordinary_note_passes(self) -> None:
        result = self.check(
            "@article{entry, author={Doe, Jane}, title={{Nested {Title}}}, "
            "year={2025}, journal={Journal}, note={Accepted manuscript}}\n"
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["warnings"], [])

    def test_title_only_misc_passes_with_advisory(self) -> None:
        result = self.check("@misc{entry, title={Unstructured source transcription}}\n")
        self.assertTrue(result["ok"])
        self.assertEqual(result["warnings"][0]["type"], "incomplete_bib_entry")
        self.assertEqual(result["warnings"][0]["missing_fields"], ["author", "year"])

    def test_organization_and_date_satisfy_creator_and_year_advisories(self) -> None:
        result = self.check(
            "@online{entry, organization={Example Org}, title={Pricing}, "
            "date={2026-01-02}, url={https://example.test}}\n"
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["warnings"], [])

    def test_parse_error_and_duplicate_key_are_fatal(self) -> None:
        result = self.check(
            "@misc{entry, title={One}, year={2024}}\n"
            "@misc{entry, title={Two}, year={2025}}\n"
            "@misc{broken title={No comma}}\n"
        )
        issue_types = {issue["type"] for issue in result["issues"]}
        self.assertIn("duplicate_bib_key", issue_types)
        self.assertIn("bib_parse_error", issue_types)

    def test_legacy_result_fields_remain_available(self) -> None:
        result = self.check("@misc{entry, author={A}, title={T}, year={2024}}\n")
        for field in (
            "project_root",
            "ok",
            "tex_files",
            "bib_files",
            "citation_count",
            "citation_keys",
            "bib_key_count",
            "issues",
        ):
            self.assertIn(field, result)

    def test_concrete_nocite_key_is_checked(self) -> None:
        result = self.check(
            "@misc{hidden, note={Reference hidden in note}}\n",
            tex_text=r"\nocite{hidden}" + "\n",
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["citation_keys"], ["hidden"])
        self.assertIn("note_only_cited_entry", {issue["type"] for issue in result["issues"]})

    def test_nocite_wildcard_checks_every_entry(self) -> None:
        result = self.check(
            "@misc{good, author={A}, title={Good}, year={2025}}\n"
            "@misc{bad, keywords={hidden}}\n",
            tex_text=r"\nocite{*}" + "\n",
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["citation_keys"], ["*"])
        bad_issues = [issue for issue in result["issues"] if issue.get("key") == "bad"]
        self.assertEqual([issue["type"] for issue in bad_issues], ["non_renderable_cited_entry"])

    def test_crossref_inherits_renderable_parent_fields(self) -> None:
        result = self.check(
            "@inproceedings{child, crossref={parent}}\n"
            "@proceedings{parent, author={Editor}, title={Proceedings}, year={2025}}\n",
            cite_key="child",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["warnings"], [])

    def test_missing_crossref_parent_is_fatal(self) -> None:
        result = self.check("@inproceedings{child, crossref={missing}}\n", cite_key="child")
        issue_types = {issue["type"] for issue in result["issues"]}
        self.assertFalse(result["ok"])
        self.assertIn("missing_crossref_parent", issue_types)

    def test_crossref_cycle_is_fatal(self) -> None:
        result = self.check(
            "@misc{first, crossref={second}}\n@misc{second, crossref={first}}\n",
            cite_key="first",
        )
        self.assertFalse(result["ok"])
        self.assertIn("crossref_cycle", {issue["type"] for issue in result["issues"]})

    def test_note_only_crossref_parent_does_not_make_child_renderable(self) -> None:
        result = self.check(
            "@misc{child, crossref={parent}}\n@misc{parent, note={Hidden reference}}\n",
            cite_key="child",
        )
        child_issues = [issue for issue in result["issues"] if issue.get("key") == "child"]
        self.assertFalse(result["ok"])
        self.assertIn("note_only_cited_entry", {issue["type"] for issue in child_issues})


class BibliographyArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.main = self.root / "thesis.tex"
        self.main.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write(self, suffix: str, text: str) -> None:
        self.main.with_suffix(suffix).write_text(text, encoding="utf-8")

    def test_no_citations_and_no_bibliography_artifacts_is_valid(self) -> None:
        self.write(".aux", r"\relax" + "\n")
        result = check_bibliography_artifacts.check_artifacts(self.root, self.main)
        self.assertTrue(result["ok"])
        self.assertFalse(result["bibliography_requested"])
        self.assertFalse(result["bbl"]["exists"])

    def test_citation_requires_bbl_and_blg(self) -> None:
        self.write(".aux", r"\citation{alpha}" + "\n" + r"\bibdata{ref/refs}" + "\n")
        result = check_bibliography_artifacts.check_artifacts(self.root, self.main)
        issue_types = {issue["type"] for issue in result["issues"]}
        self.assertFalse(result["ok"])
        self.assertIn("missing_bbl_file", issue_types)
        self.assertIn("missing_blg_file", issue_types)
        self.assertIn("missing_bbl_entry", issue_types)

    def test_normal_bbl_and_blg_cover_citations(self) -> None:
        self.write(".aux", r"\citation{alpha,beta}" + "\n" + r"\bibdata{ref/refs}" + "\n")
        self.write(
            ".bbl",
            "\\begin{thebibliography}{2}\n"
            "\\bibitem[Author(2024)]{alpha}\nAuthor.\\newblock Title[A].\\newblock 2024.\n"
            "\\bibitem{beta}\nOrg.\\newblock Web page[EB/OL].\n"
            "\\end{thebibliography}\n",
        )
        self.write(".blg", "You've used 2 entries,\nwarning$ -- 0\n")
        result = check_bibliography_artifacts.check_artifacts(self.root, self.main)
        self.assertTrue(result["ok"])
        self.assertEqual(result["bbl"]["bibitem_count"], 2)
        self.assertEqual(result["issues"], [])

    def test_empty_and_z_only_bibitems_fail(self) -> None:
        self.write(".aux", r"\citation{empty,zonly}" + "\n" + r"\bibdata{ref/refs}" + "\n")
        self.write(
            ".bbl",
            "\\begin{thebibliography}{2}\n"
            "\\bibitem{empty}\n\\newblock\n"
            "\\bibitem{zonly}\n\\newblock \\allowbreak[Z].\n"
            "\\end{thebibliography}\n",
        )
        self.write(".blg", "warning$ -- 0\n")
        result = check_bibliography_artifacts.check_artifacts(self.root, self.main)
        issue_types = {issue["type"] for issue in result["issues"]}
        self.assertFalse(result["ok"])
        self.assertIn("empty_bibitem", issue_types)
        self.assertIn("z_only_bibitem", issue_types)

    def test_blg_warning_is_advisory_but_error_is_fatal(self) -> None:
        self.write(".aux", r"\citation{alpha}" + "\n" + r"\bibdata{ref/refs}" + "\n")
        self.write(
            ".bbl",
            "\\begin{thebibliography}{1}\n\\bibitem{alpha}\nVisible.\n\\end{thebibliography}\n",
        )
        self.write(".blg", "Warning--empty year in alpha\n")
        warning_result = check_bibliography_artifacts.check_artifacts(self.root, self.main)
        self.assertTrue(warning_result["ok"])
        self.assertEqual(warning_result["warnings"][0]["type"], "bibtex_log_warning")

        self.write(".blg", "I couldn't open database file missing.bib\n")
        error_result = check_bibliography_artifacts.check_artifacts(self.root, self.main)
        self.assertFalse(error_result["ok"])
        self.assertIn("bibtex_log_error", {issue["type"] for issue in error_result["issues"]})

    def test_stale_bibliography_artifacts_are_advisory_without_current_request(self) -> None:
        self.write(".aux", r"\relax" + "\n")
        self.write(
            ".bbl",
            "\\begin{thebibliography}{1}\n"
            "\\bibitem{old}\n\\newblock \\allowbreak[Z].\n"
            "\\end{thebibliography}\n",
        )
        self.write(".blg", "I couldn't open database file old.bib\n")
        result = check_bibliography_artifacts.check_artifacts(self.root, self.main)
        self.assertTrue(result["ok"])
        self.assertEqual(result["issues"], [])
        self.assertTrue(result["bbl"]["stale"])
        self.assertTrue(result["blg"]["stale"])
        self.assertEqual(
            [warning["type"] for warning in result["warnings"]],
            ["stale_bibliography_artifact", "stale_bibliography_artifact"],
        )

    def test_nested_optional_bibitem_label_keeps_key_and_detects_z_only_body(self) -> None:
        self.write(".aux", r"\citation{alpha}" + "\n" + r"\bibdata{ref/refs}" + "\n")
        self.write(
            ".bbl",
            "\\begin{thebibliography}{1}\n"
            r"\bibitem[{{Org [OpenAI]} \[escaped\] [nested]}]{alpha}" + "\n"
            "\\newblock \\allowbreak[Z].\n"
            "\\end{thebibliography}\n",
        )
        self.write(".blg", "warning$ -- 0\n")
        result = check_bibliography_artifacts.check_artifacts(self.root, self.main)
        issue_types = {issue["type"] for issue in result["issues"]}
        self.assertFalse(result["ok"])
        self.assertEqual(result["bbl"]["keys"], ["alpha"])
        self.assertIn("z_only_bibitem", issue_types)
        self.assertNotIn("missing_bbl_entry", issue_types)


if __name__ == "__main__":
    unittest.main()
