from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from escape_latex_text import (  # noqa: E402
    escape_latex,
    escape_latex_preserving_math,
    escape_markdown_text,
)


class EscapeLatexTests(unittest.TestCase):
    def test_plain_escape_api_is_unchanged(self):
        self.assertEqual(escape_latex("a_b%"), r"a\_b\%")

    def test_required_escaped_price_math_regression(self):
        source = r"$C_{\min}=\$0.71$ 和 $C_{\max}=\$1.71$"
        self.assertEqual(escape_latex_preserving_math(source), source)
        self.assertEqual(escape_markdown_text(source), source)

    def test_literal_prices_and_unclosed_math_are_safe(self):
        self.assertEqual(escape_latex_preserving_math("$5 与 $10"), r"\$5 与 \$10")
        self.assertEqual(escape_markdown_text("未闭合 $x"), r"未闭合 \$x")

    def test_literal_price_before_formula_does_not_swallow_formula(self):
        source = "price $5, formula $x$"
        self.assertEqual(escape_markdown_text(source), r"price \$5, formula $x$")

    def test_code_math_is_escaped_and_real_math_is_preserved(self):
        source = "`$code$` and $x_1$"
        self.assertEqual(escape_markdown_text(source), r"`\$code\$` and $x_1$")

    def test_multiline_code_math_is_escaped_not_preserved(self):
        source = "`code\n$x$\n` and $y$"
        self.assertEqual(escape_markdown_text(source), "`code\n\\$x\\$\n` and $y$")

    def test_display_math_can_cross_lines(self):
        source = "before_\n$$\nx_1 + y_2\n$$\nafter%"
        expected = "before\\_\n$$\nx_1 + y_2\n$$\nafter\\%"
        self.assertEqual(escape_latex_preserving_math(source), expected)

    def test_math_aware_cli_is_compatible(self):
        source = r"$x_1$ & text"
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "escape_latex_text.py"), "--math-aware", "--text", source],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "$x_1$ \\& text\n")


if __name__ == "__main__":
    unittest.main()
