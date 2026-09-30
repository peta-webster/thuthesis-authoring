from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_latex_safety  # noqa: E402


class LatexBraceSafetyTests(unittest.TestCase):
    def check_text(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chapter.tex"
            path.write_text(text, encoding="utf-8")
            return check_latex_safety.check_file(path)

    def test_reversed_braces_fail_with_source_location(self):
        result = self.check_text("Complete.\n  }{\n")
        self.assertFalse(result["ok"])
        issue = next(item for item in result["issues"] if item["type"] == "unexpected_closing_brace")
        self.assertEqual((issue["line"], issue["column"]), (2, 3))

    def test_balanced_group_after_unmatched_close_is_not_reported_again(self):
        result = self.check_text("}{}\n")
        closings = [item for item in result["issues"] if item["type"] == "unexpected_closing_brace"]
        self.assertEqual([(item["line"], item["column"]) for item in closings], [(1, 1)])

    def test_balanced_nested_and_escaped_braces_pass(self):
        self.assertTrue(self.check_text(r"\section{A {nested} title} \{literal\}")["ok"])

    def test_comments_and_literal_code_do_not_cause_brace_errors(self):
        source = "% }{\n\\verb|}{|\n\\begin{verbatim}\n}{\n\\end{verbatim}\n{Valid}\n"
        self.assertTrue(self.check_text(source)["ok"])
        result = self.check_text(source + "  }{\n")
        issue = next(item for item in result["issues"] if item["type"] == "unexpected_closing_brace")
        self.assertEqual((issue["line"], issue["column"]), (7, 3))

    def test_net_balance_api_and_existing_imbalance_diagnostic_remain(self):
        for text, balance in [("{", 1), ("}", -1), ("}{", 0), (r"\{", 0), (r"\\{", 1)]:
            with self.subTest(text=text):
                self.assertEqual(check_latex_safety.brace_balance(text), balance)
        result = self.check_text("{")
        self.assertFalse(result["ok"])
        self.assertIn("brace_balance", {item["type"] for item in result["issues"]})

    def test_cli_rejects_reversed_braces(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chapter.tex"
            path.write_text("}{\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPTS / "check_latex_safety.py"), str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(json.loads(result.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
