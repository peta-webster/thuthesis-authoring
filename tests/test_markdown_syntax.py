from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _markdown_syntax import (  # noqa: E402
    parse_markdown_row,
    parse_pipe_alignments,
    scan_markdown_math,
    scan_pipe_tables,
    split_pipe_row,
)


class MarkdownMathScannerTests(unittest.TestCase):
    def test_escaped_dollars_inside_adjacent_math_spans(self):
        text = r"$C_{\min}=\$0.71$ 和 $C_{\max}=\$1.71$"
        spans, issues = scan_markdown_math(text)
        self.assertEqual(
            [span.text for span in spans],
            [r"$C_{\min}=\$0.71$", r"$C_{\max}=\$1.71$"],
        )
        self.assertFalse(issues)

    def test_display_crosses_lines_but_inline_does_not(self):
        text = "$x\n+1$\n$$\nx+1\n$$"
        spans, issues = scan_markdown_math(text)
        self.assertEqual([span.kind for span in spans], ["display"])
        self.assertEqual((spans[0].start_line, spans[0].end_line), (3, 5))
        self.assertTrue(any(issue.kind == "inline" for issue in issues))

    def test_code_and_literal_prices_are_not_math(self):
        text = "`$inline$`\n```tex\n$code$\n```\n价格 $5 与 $10"
        spans, _ = scan_markdown_math(text)
        self.assertEqual(spans, [])

    def test_inline_code_span_can_cross_physical_lines(self):
        text = "`code\n$x$\n` and $y$"
        spans, _ = scan_markdown_math(text)
        self.assertEqual([span.text for span in spans], ["$y$"])

    def test_unmatched_multiline_backtick_does_not_hide_later_math(self):
        text = "`unmatched\n$x$\n"
        spans, _ = scan_markdown_math(text)
        self.assertEqual([span.text for span in spans], ["$x$"])

    def test_math_opener_precedes_fenced_code_looking_tokens(self):
        text = "$$\nbefore\n```text\ncode\n```\nafter\n$$"
        spans, issues = scan_markdown_math(text)
        self.assertEqual([span.kind for span in spans], ["display"])
        self.assertFalse(issues)

    def test_math_opener_precedes_multiline_inline_code_looking_tokens(self):
        text = "$$ before `code\n$hidden$\n` after $$"
        spans, issues = scan_markdown_math(text)
        self.assertEqual([span.kind for span in spans], ["display"])
        self.assertFalse(issues)

    def test_math_opener_precedes_inline_code_looking_span(self):
        text = "$before `code` after$ and $ok$"
        spans, issues = scan_markdown_math(text)
        self.assertEqual([span.text for span in spans], ["$before `code` after$", "$ok$"])
        self.assertFalse(issues)

    def test_pandoc_inline_boundary_rules(self):
        spans, _ = scan_markdown_math("$ x$ / $x $ / $x$2 / $x$ 正常")
        self.assertEqual([span.text for span in spans], ["$x$"])

    def test_rejected_price_closer_is_reconsidered_as_formula_opener(self):
        spans, issues = scan_markdown_math("price $5, formula $x$")
        self.assertEqual([span.text for span in spans], ["$x$"])
        self.assertEqual(len(issues), 1)
        self.assertLessEqual(issues[0].end, spans[0].start)


class MarkdownPipeTableScannerTests(unittest.TestCase):
    def test_valid_table_caption_alignment_and_line_range(self):
        text = (
            "intro\n"
            "**表 2：示例标题。**\n\n"
            "| 左 | 中 | 右 |\n"
            "| :--- | :---: | ---: |\n"
            "| a | b | c |\n"
        )
        tables = scan_pipe_tables(text)
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertTrue(table.valid)
        self.assertEqual((table.start_line, table.end_line), (4, 6))
        self.assertEqual(table.caption_line, 2)
        self.assertEqual(table.caption, "示例标题。")
        self.assertEqual(table.alignments, ["l", "c", "r"])

    def test_escaped_pipe_does_not_split_cell(self):
        self.assertEqual(split_pipe_row(r"| a \| b | c |"), [r"a \| b", "c"])
        self.assertEqual(parse_pipe_alignments("| :--- | ---: |"), ["l", "r"])

    def test_general_rows_allow_optional_outer_pipes_without_changing_v1_splitter(self):
        self.assertEqual(split_pipe_row("A | B"), [])
        self.assertEqual(parse_markdown_row("A | B"), ["A", "B"])
        self.assertEqual(parse_markdown_row("| A | B"), ["A", "B"])
        self.assertEqual(parse_markdown_row("A | B |"), ["A", "B"])

    def test_general_row_respects_odd_even_backslashes(self):
        self.assertEqual(parse_markdown_row(r"A \| B | C"), [r"A \| B", "C"])
        self.assertEqual(parse_markdown_row(r"A \\| B | C"), ["A " + "\\\\", "B", "C"])

    def test_malformed_width_is_one_preserved_region(self):
        text = "| A | B |\n| --- | --- |\n| 1 | 2 | 3 |\n"
        tables = scan_pipe_tables(text)
        self.assertEqual(len(tables), 1)
        self.assertFalse(tables[0].valid)
        self.assertEqual(tables[0].reason_code, "markdown_table_row_width_mismatch")
        self.assertEqual(tables[0].source_text, text.rstrip("\n"))

    def test_trailing_table_like_row_is_included_before_width_validation(self):
        text = "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 |\n"
        tables = scan_pipe_tables(text)
        self.assertEqual(len(tables), 1)
        self.assertEqual((tables[0].start_line, tables[0].end_line), (1, 4))
        self.assertFalse(tables[0].valid)
        self.assertEqual(tables[0].source_text, text.rstrip("\n"))

    def test_suspicious_single_outer_pipe_rows_extend_existing_region(self):
        for final_row in ("bad |", "| bad"):
            with self.subTest(final_row=final_row):
                text = f"| A | B |\n| --- | --- |\n| 1 | 2 |\n{final_row}\n"
                table = scan_pipe_tables(text)[0]
                self.assertEqual(table.end_line, 4)
                self.assertFalse(table.valid)
                self.assertEqual(table.reason_code, "markdown_table_row_width_mismatch")
                self.assertEqual(table.source_text, text.rstrip("\n"))

    def test_single_sided_final_row_is_valid_when_width_matches(self):
        text = "| A | B |\n| --- | --- |\n| 1 | 2\n"
        tables = scan_pipe_tables(text)
        self.assertTrue(tables[0].valid)
        self.assertEqual(tables[0].rows, [["1", "2"]])

    def test_unsafe_cell_objects_block_conversion_but_math_does_not(self):
        cases = {
            "![plot](plot.png)": "markdown_table_image_requires_review",
            "[^note]": "markdown_table_footnote_requires_review",
            "[^note]: detail": "markdown_table_footnote_requires_review",
            "`code`": "markdown_table_code_requires_review",
            "*emphasis*": "markdown_table_emphasis_requires_review",
            "**strong**": "markdown_table_emphasis_requires_review",
            "_emphasis_": "markdown_table_emphasis_requires_review",
            "__strong__": "markdown_table_emphasis_requires_review",
            "[label][source]": "markdown_table_reference_link_requires_review",
            "[label][]": "markdown_table_reference_link_requires_review",
            "<span>raw</span>": "markdown_table_html_requires_review",
        }
        for cell, reason in cases.items():
            with self.subTest(cell=cell):
                table = scan_pipe_tables(f"A | B\n--- | ---\n{cell} | $x$\n")[0]
                self.assertFalse(table.valid)
                self.assertEqual(table.reason_code, reason)
        self.assertTrue(scan_pipe_tables("A | B\n--- | ---\n$x$ | y\n")[0].valid)

    def test_escaped_markup_and_math_are_safe_table_cell_content(self):
        cells = (
            r"\`literal\`",
            r"\*literal\*",
            r"\[label\]\[source\]",
            r"$x_1^*$",
            "snake_case",
            r"A \| B",
        )
        for cell in cells:
            with self.subTest(cell=cell):
                table = scan_pipe_tables(f"A | B\n--- | ---\n{cell} | plain\n")[0]
                self.assertTrue(table.valid, table.reason_code)

    def test_fenced_pipe_rows_are_ignored(self):
        text = "~~~\n| A | B |\n| --- | --- |\n~~~\n"
        self.assertEqual(scan_pipe_tables(text), [])

    def test_long_fence_is_not_closed_by_shorter_backtick_run(self):
        text = "````markdown\n```\n| A | B |\n| --- | --- |\n```\n````\n"
        self.assertEqual(scan_pipe_tables(text), [])

    def test_fence_marker_with_info_is_content_not_closer(self):
        text = "```markdown\n```python\n| A | B |\n| --- | --- |\n```\n"
        self.assertEqual(scan_pipe_tables(text), [])


if __name__ == "__main__":
    unittest.main()
