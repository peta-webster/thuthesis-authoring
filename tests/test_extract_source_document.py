import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from extract_source_document import (  # noqa: E402
    analyze_markdown,
    parse_markdown,
    unescape_pandoc_markdown,
)


class ExtractMarkdownTests(unittest.TestCase):
    SAMPLE = (
        "# 标题\n\n"
        "正文有 $x_1$。\n\n"
        "**表 1：数据。**\n\n"
        "| A | B |\n"
        "| --- | ---: |\n"
        "| 1 | 2 |\n"
    )

    def test_native_math_is_advisory_and_table_is_candidate(self):
        analysis = analyze_markdown(self.SAMPLE)
        self.assertEqual(analysis["detected_math"]["inline_count"], 1)
        self.assertEqual(len(analysis["conversion_candidates"]), 1)
        self.assertFalse(any(item["type"] == "equation" for item in analysis["manual_review"]))
        self.assertFalse(any(item["type"] == "table" for item in analysis["manual_review"]))
        self.assertTrue(any(block["type"] == "table" for block in analysis["blocks"]))
        self.assertTrue(all(not item["requires_todo"] for item in analysis["review_advisories"]))

    def test_pandoc_docx_objects_remain_manual(self):
        analysis = analyze_markdown(self.SAMPLE, source_kind="pandoc-docx")
        self.assertEqual(analysis["conversion_candidates"], [])
        reasons = {item["reason_code"] for item in analysis["manual_review"]}
        self.assertIn("word_table_requires_review", reasons)
        self.assertIn("word_omml_equation_requires_review", reasons)
        self.assertTrue(all(item["requires_todo"] for item in analysis["manual_review"]))

    def test_malformed_table_is_preserved_with_schema_v2_locations(self):
        source = "| A | B |\n| --- | --- |\n| 1 | 2 | 3 |\n"
        analysis = analyze_markdown(source)
        self.assertEqual(analysis["blocks"][0]["text"], source.rstrip("\n"))
        item = analysis["manual_review"][0]
        self.assertEqual((item["start_line"], item["end_line"]), (1, 3))
        self.assertEqual(item["reason_code"], "markdown_table_row_width_mismatch")
        self.assertIn("recommended_tool", item)

    def test_unsafe_table_cell_is_full_manual_review_not_candidate(self):
        source = "A | B\n--- | ---\n![plot](plot.png) | $x$\n"
        analysis = analyze_markdown(source)
        self.assertEqual(analysis["conversion_candidates"], [])
        item = next(entry for entry in analysis["manual_review"] if entry["type"] == "table")
        self.assertEqual(item["reason_code"], "markdown_table_image_requires_review")
        self.assertEqual(item["source_text"], source.rstrip("\n"))
        self.assertEqual(item["recommended_tool"], "manual Markdown table object review")
        self.assertIn("嵌套对象", item["message"])

    def test_nested_table_markup_has_stable_manual_reason_codes(self):
        cases = {
            "`code`": "markdown_table_code_requires_review",
            "*emphasis*": "markdown_table_emphasis_requires_review",
            "_emphasis_": "markdown_table_emphasis_requires_review",
            "[label][source]": "markdown_table_reference_link_requires_review",
        }
        for cell, reason in cases.items():
            with self.subTest(cell=cell):
                source = f"A | B\n--- | ---\n{cell} | $x_1$\n"
                analysis = analyze_markdown(source)
                self.assertEqual(analysis["conversion_candidates"], [])
                table_item = next(
                    item for item in analysis["manual_review"] if item["type"] == "table"
                )
                self.assertEqual(table_item["reason_code"], reason)
                self.assertEqual(
                    table_item["recommended_tool"],
                    "manual Markdown table object review",
                )
                self.assertIn("嵌套对象", table_item["message"])

    def test_v1_parse_markdown_tuple_remains_available(self):
        blocks, manual = parse_markdown("# H\ntext\n")
        self.assertIsInstance(blocks, list)
        self.assertIsInstance(manual, list)
        self.assertEqual(blocks[0]["type"], "heading")

    def test_pandoc_preprocessing_preserves_dollar_and_pipe_escapes(self):
        source = r"price \$5 and a \| b and \[12\]"
        self.assertEqual(unescape_pandoc_markdown(source), source)

    def test_unclosed_math_requires_todo_but_literal_price_does_not(self):
        unclosed = analyze_markdown("公式 $x+1\n")
        self.assertTrue(any(
            item["reason_code"] == "unclosed_markdown_math" and item["requires_todo"]
            for item in unclosed["manual_review"]
        ))

        price = analyze_markdown("价格 $5 与 $10\n")
        self.assertFalse(any(
            item["reason_code"] == "unclosed_markdown_math"
            for item in price["manual_review"]
        ))
        self.assertTrue(any(
            item["reason_code"] == "literal_dollar_price_detected"
            for item in price["review_advisories"]
        ))

    def test_numeric_unclosed_math_is_not_misclassified_as_price(self):
        for source in ("公式 $5 + x\n", "公式 $10^2\n"):
            with self.subTest(source=source):
                analysis = analyze_markdown(source)
                self.assertTrue(any(
                    item["reason_code"] == "unclosed_markdown_math"
                    for item in analysis["manual_review"]
                ))
                self.assertFalse(any(
                    item["reason_code"] == "literal_dollar_price_detected"
                    for item in analysis["review_advisories"]
                ))

    def test_price_with_prose_context_remains_advisory(self):
        analysis = analyze_markdown("成本 $5，与上一版相同。\n")
        self.assertFalse(any(
            item["reason_code"] == "unclosed_markdown_math"
            for item in analysis["manual_review"]
        ))
        self.assertTrue(any(
            item["reason_code"] == "literal_dollar_price_detected"
            for item in analysis["review_advisories"]
        ))

    def test_four_backtick_fence_is_shared_and_shorter_run_is_content(self):
        source = (
            "````markdown\n"
            "```\n"
            "# 围栏内标题\n"
            "| A | B |\n"
            "| --- | --- |\n"
            "```\n"
            "````\n"
            "# 围栏外标题\n"
            "围栏外正文\n"
        )
        analysis = analyze_markdown(source)
        self.assertEqual(
            [block["text"] for block in analysis["blocks"]],
            ["围栏外标题", "围栏外正文"],
        )
        self.assertEqual(analysis["conversion_candidates"], [])

    def test_fence_marker_with_info_string_does_not_close_block(self):
        source = (
            "```markdown\n"
            "```python\n"
            "# 仍在围栏内\n"
            "```\n"
            "# 外部\n"
        )
        analysis = analyze_markdown(source)
        self.assertEqual([block["text"] for block in analysis["blocks"]], ["外部"])

    def test_cli_keeps_old_fields_and_adds_schema_v2_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.md"
            path.write_text(self.SAMPLE, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "extract_source_document.py"), str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        for legacy in ("ok", "source", "format", "extractor", "blocks", "manual_review"):
            self.assertIn(legacy, result)
        self.assertEqual(result["schema_version"], 2)
        self.assertIn("detected_math", result)
        self.assertIn("conversion_candidates", result)
        self.assertIn("review_advisories", result)


if __name__ == "__main__":
    unittest.main()
