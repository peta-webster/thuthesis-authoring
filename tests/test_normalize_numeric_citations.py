from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_numeric_citations import normalize_numeric_citations_with_count  # noqa: E402


class NumericCitationTests(unittest.TestCase):
    def test_math_is_preserved_between_prose_citations(self):
        source = "见[3]，区间 $x \\in [1,2]$，参见[4]。\n$$\nx \\in [5,6]\n$$\n见[7]。\n"
        expected = "见\\cite{src3}，区间 $x \\in [1,2]$，参见\\cite{src4}。\n$$\nx \\in [5,6]\n$$\n见\\cite{src7}。\n"
        self.assertEqual(normalize_numeric_citations_with_count(source, "src"), (expected, 3))

    def test_inline_and_fenced_code_are_preserved(self):
        protected_regions = [
            "`arr[1]`",
            "``arr[1] + `literal` ``",
            "`arr[1]\narr[2]`",
            "```python\narr[1]\n```",
            "~~~python\narr[1]\n~~~",
            "````text\narr[1]\n```\narr[2]\n````",
        ]
        for protected in protected_regions:
            with self.subTest(protected=protected):
                source = "见[3]。\n" + protected + "\n见[4]。"
                expected = "见\\cite{src3}。\n" + protected + "\n见\\cite{src4}。"
                self.assertEqual(normalize_numeric_citations_with_count(source, "src"), (expected, 2))

    def test_reference_lines_escapes_and_numeric_variants_remain_compatible(self):
        source = "[1] Original reference\r\n见［１，２］、【3–4】，保留 \\[5]。\r\n代码 `arr[6]`，见[7]。"
        expected = "[1] Original reference\r\n见\\cite{src1,src2}、\\cite{src3,src4}，保留 \\[5]。\r\n代码 `arr[6]`，见\\cite{src7}。"
        self.assertEqual(normalize_numeric_citations_with_count(source, "src"), (expected, 3))

    def test_literal_price_does_not_hide_prose_citations(self):
        source = r"价格 \$5，参见[1]，公式 $x \in [2,3]$。"
        expected = r"价格 \$5，参见\cite{src1}，公式 $x \in [2,3]$。"
        self.assertEqual(normalize_numeric_citations_with_count(source, "src"), (expected, 1))

    def test_file_cli_dry_run_and_in_place_preserve_source_objects(self):
        source = "见[3]，$x \\in [1,2]$，`arr[1]`。\n"
        expected = "见\\cite{src3}，$x \\in [1,2]$，`arr[1]`。\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.md"
            path.write_text(source, encoding="utf-8")
            command = [sys.executable, str(SCRIPTS / "normalize_numeric_citations.py"), "--prefix", "src", str(path)]
            for in_place in (False, True):
                result = subprocess.run(command + (["--in-place"] if in_place else []), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertTrue(report["ok"])
                self.assertEqual(report["results"][0]["replacements"], 1)
                self.assertEqual(path.read_text(encoding="utf-8"), expected if in_place else source)


if __name__ == "__main__":
    unittest.main()
