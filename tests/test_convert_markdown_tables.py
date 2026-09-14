import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from convert_markdown_tables import (  # noqa: E402
    convert_markdown_tables,
    parse_alignments,
    split_row,
)
from extract_source_document import analyze_markdown  # noqa: E402


class ConvertMarkdownTablesTests(unittest.TestCase):
    def test_compatibility_wrappers(self):
        self.assertEqual(split_row(r"| a \| b | c |"), [r"a \| b", "c"])
        self.assertEqual(parse_alignments("| :--- | :---: | ---: |"), ["l", "c", "r"])
        self.assertEqual(parse_alignments("| ordinary | row: |"), ["l", "r"])

    def test_valid_table_uses_caption_and_escapes_cells(self):
        source = (
            "**表 3：价格画像。**\n\n"
            "| 模型 | 价格 | 公式 |\n"
            "| --- | ---: | :---: |\n"
            "| A \\| B | \\$5 | $x_1$ |\n"
        )
        converted, count = convert_markdown_tables(source, label_prefix="case")
        self.assertEqual(count, 1)
        self.assertIn(r"\caption{价格画像}", converted)
        self.assertIn(r"\label{tab:case1}", converted)
        self.assertIn(r"A | B & \$5 & $x_1$", converted)

    def test_malformed_table_is_preserved_without_truncation(self):
        source = "| A | B |\n| --- | --- |\n| 1 | 2 | 3 |\n"
        converted, count = convert_markdown_tables(source)
        self.assertEqual(count, 0)
        self.assertEqual(converted, source)

    def test_single_outer_pipe_bad_row_prevents_valid_prefix_conversion(self):
        for final_row in ("bad |", "| bad"):
            with self.subTest(final_row=final_row):
                source = f"| A | B |\n| --- | --- |\n| 1 | 2 |\n{final_row}\n"
                converted, count = convert_markdown_tables(source)
                self.assertEqual(count, 0)
                self.assertEqual(converted, source)

    def test_numbering_continues_across_calls(self):
        table = "| A |\n| --- |\n| 1 |\n"
        first, index = convert_markdown_tables(table, "multi", 0)
        second, index = convert_markdown_tables(table, "multi", index)
        self.assertIn("tab:multi1", first)
        self.assertIn("tab:multi2", second)
        self.assertEqual(index, 2)

    def test_extractor_and_converter_share_validity_decision(self):
        valid = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
        invalid = "| A | B |\n| --- | --- |\n| 1 | 2 | 3 |\n"
        self.assertEqual(len(analyze_markdown(valid)["conversion_candidates"]), 1)
        self.assertEqual(convert_markdown_tables(valid)[1], 1)
        self.assertEqual(len(analyze_markdown(invalid)["conversion_candidates"]), 0)
        self.assertEqual(convert_markdown_tables(invalid)[1], 0)

    def test_optional_outer_pipes_convert(self):
        source = "A | B\n--- | ---:\n1 | 2\n"
        converted, count = convert_markdown_tables(source, "outer")
        self.assertEqual(count, 1)
        self.assertIn("tab:outer1", converted)
        self.assertIn("1 & 2", converted)

    def test_unsafe_cell_object_preserves_complete_source(self):
        for cell in (
            "![plot](plot.png)",
            "[^note]",
            "[^note]: detail",
            "`code`",
            "*emphasis*",
            "**strong**",
            "_emphasis_",
            "__strong__",
            "[label][source]",
            "[label][]",
            "<span>raw</span>",
        ):
            with self.subTest(cell=cell):
                source = f"A | B\n--- | ---\n{cell} | $x$\n"
                converted, count = convert_markdown_tables(source)
                self.assertEqual(count, 0)
                self.assertEqual(converted, source)

    def test_file_argument_is_dry_run_without_in_place(self):
        source = "| A |\n| --- |\n| 1 |\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chapter.md"
            path.write_text(source, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "convert_markdown_tables.py"), str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
            after = path.read_text(encoding="utf-8")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["results"][0]["changed"])
        self.assertEqual(result["results"][0]["tables_converted"], 1)
        self.assertEqual(after, source)


if __name__ == "__main__":
    unittest.main()
