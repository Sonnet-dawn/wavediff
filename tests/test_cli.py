"""End-to-end CLI tests, including the exit-code contract CI depends on."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from wavediff.cli import EXIT_DIVERGED, EXIT_ERROR, EXIT_IDENTICAL, main

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "golden.vcd"
DIVERGED = FIXTURES / "diverged.vcd"
SHIFTED = FIXTURES / "shifted.vcd"

# Written inside the repo rather than the system temp dir so the suite works
# in sandboxes that only permit writes under the project.
TMP_ROOT = Path(__file__).parent / "_tmp"


class TestExitCodes(unittest.TestCase):
    def test_identical_waveforms_exit_zero(self) -> None:
        self.assertEqual(main([str(GOLDEN), str(GOLDEN), "-q"]), EXIT_IDENTICAL)

    def test_diverged_waveforms_exit_one(self) -> None:
        self.assertEqual(main([str(GOLDEN), str(DIVERGED), "-q"]), EXIT_DIVERGED)

    def test_shifted_waveforms_are_realigned_and_exit_zero(self) -> None:
        self.assertEqual(main([str(GOLDEN), str(SHIFTED), "-q"]), EXIT_IDENTICAL)

    def test_exit_zero_flag_suppresses_the_failure_code(self) -> None:
        self.assertEqual(
            main([str(GOLDEN), str(DIVERGED), "-q", "--exit-zero"]), EXIT_IDENTICAL
        )

    def test_missing_file_exits_two(self) -> None:
        self.assertEqual(main(["nope.vcd", str(GOLDEN), "-q"]), EXIT_ERROR)

    def test_unknown_alignment_mode_exits_two(self) -> None:
        with self.assertRaises(SystemExit):
            main([str(GOLDEN), str(GOLDEN), "--align", "teleport"])


class TestReports(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TMP_ROOT / "reports"
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True, exist_ok=True)

    def test_html_report_is_written_and_self_contained(self) -> None:
        out = self.tmp / "r.html"
        code = main([str(GOLDEN), str(DIVERGED), "-q", "--html", str(out)])
        self.assertEqual(code, EXIT_DIVERGED)
        html = out.read_text(encoding="utf-8")
        self.assertIn("DIVERGED", html)
        self.assertIn("tb.dut.count", html)
        self.assertIn("<svg", html)
        # No external resources: the file must work offline from a shared drive.
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("<script", html)

    def test_identical_html_report_says_so(self) -> None:
        out = self.tmp / "same.html"
        main([str(GOLDEN), str(GOLDEN), "-q", "--html", str(out)])
        self.assertIn("IDENTICAL", out.read_text(encoding="utf-8"))

    def test_html_report_renders_a_bus_signal(self) -> None:
        out = self.tmp / "bus.html"
        main([str(GOLDEN), str(DIVERGED), "-q", "--html", str(out)])
        self.assertIn("8 bits", out.read_text(encoding="utf-8"))

    def test_json_result_is_machine_readable(self) -> None:
        out = self.tmp / "r.json"
        main([str(GOLDEN), str(DIVERGED), "-q", "--json", str(out)])
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertFalse(payload["identical"])
        self.assertEqual(payload["first_divergence"], 30)
        self.assertEqual(payload["counts"]["differ"], 1)
        count = next(s for s in payload["signals"] if s["name"] == "tb.dut.count")
        self.assertEqual(count["intervals"][0]["start"], 30)
        self.assertEqual(count["intervals"][0]["end"], 40)

    def test_report_directory_is_created(self) -> None:
        out = self.tmp / "nested" / "deep" / "r.html"
        main([str(GOLDEN), str(DIVERGED), "-q", "--html", str(out)])
        self.assertTrue(out.exists())

    def test_default_radix_pads_bus_values_to_width(self) -> None:
        out = self.tmp / "bin.html"
        main([str(GOLDEN), str(DIVERGED), "-q", "--html", str(out)])
        html = out.read_text(encoding="utf-8")
        self.assertIn("00000011", html)  # A
        self.assertIn("00000111", html)  # B

    def test_hex_radix_reformats_bus_values(self) -> None:
        out = self.tmp / "hex.html"
        main([str(GOLDEN), str(DIVERGED), "-q", "--html", str(out), "--radix", "hex"])
        html = out.read_text(encoding="utf-8")
        self.assertIn(">03<", html)
        self.assertIn(">07<", html)

    def test_decimal_radix_appears_in_the_text_summary(self) -> None:
        # Capture stdout to assert on the human-facing summary.
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            main([str(GOLDEN), str(DIVERGED), "--radix", "dec"])
        text = buf.getvalue()
        self.assertIn("DIVERGED", text)
        self.assertIn("tb.dut.count", text)
        self.assertIn("A=3", text)
        self.assertIn("B=7", text)


class TestSignalSelection(unittest.TestCase):
    def test_filtering_out_the_broken_signal_hides_the_difference(self) -> None:
        code = main(
            [str(GOLDEN), str(DIVERGED), "-q", "--signals", r"^tb\.(clk|rst_n)$"]
        )
        self.assertEqual(code, EXIT_IDENTICAL)

    def test_no_matching_signals_is_an_error(self) -> None:
        code = main([str(GOLDEN), str(DIVERGED), "-q", "--signals", "^nothing\\.here$"])
        self.assertEqual(code, EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
