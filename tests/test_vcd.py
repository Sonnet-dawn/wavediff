"""Parser tests: declarations, hierarchy, values, initial state."""

from __future__ import annotations

import itertools
import unittest
from pathlib import Path

from wavediff import format_value, read_vcd
from wavediff.model import normalize_value
from wavediff.vcd import VcdParseError

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "golden.vcd"

# Scratch files live next to the tests rather than in the system temp dir, so
# the suite runs identically in sandboxes that only allow writes to the repo.
TMP_ROOT = Path(__file__).parent / "_tmp"
_counter = itertools.count()


def write_vcd(text: str) -> Path:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TMP_ROOT / f"parser_{next(_counter)}.vcd"
    path.write_text(text, encoding="utf-8")
    return path


class TestParseGolden(unittest.TestCase):
    def setUp(self) -> None:
        self.wave = read_vcd(GOLDEN)

    def test_hierarchy_is_qualified(self) -> None:
        self.assertIn("tb.clk", self.wave.signals)
        self.assertIn("tb.dut.count", self.wave.signals)
        self.assertIn("tb.dut.valid", self.wave.signals)

    def test_widths_and_kinds(self) -> None:
        self.assertEqual(self.wave.signals["tb.clk"].width, 1)
        self.assertEqual(self.wave.signals["tb.dut.count"].width, 8)
        self.assertEqual(self.wave.signals["tb.clk"].kind, "wire")

    def test_timescale(self) -> None:
        self.assertEqual(self.wave.timescale, "1ns")

    def test_t_zero_values_become_initial_state_not_transitions(self) -> None:
        count = self.wave.traces["tb.dut.count"]
        self.assertEqual(count.initial, "0")
        self.assertNotIn(0, count.times)

    def test_transitions_match_the_dump(self) -> None:
        # Values are stored in normalised binary: b00000010 -> "10".
        count = self.wave.traces["tb.dut.count"]
        self.assertEqual(count.times, [11, 20, 30, 40])
        self.assertEqual(count.values, ["1", "10", "11", "100"])

    def test_value_at_samples_arbitrary_times(self) -> None:
        count = self.wave.traces["tb.dut.count"]
        self.assertEqual(count.value_at(0), "0")
        self.assertEqual(count.value_at(10), "0")
        self.assertEqual(count.value_at(11), "1")
        self.assertEqual(count.value_at(29), "10")
        self.assertEqual(count.value_at(9999), "100")

    def test_max_time(self) -> None:
        self.assertEqual(self.wave.max_time, 51)


class TestSignalFiltering(unittest.TestCase):
    def test_pattern_restricts_retained_traces(self) -> None:
        wave = read_vcd(GOLDEN, signals=[r"^tb\.dut\."])
        self.assertEqual(set(wave.traces), {"tb.dut.count", "tb.dut.valid"})
        # Declarations are still fully known, only storage is filtered.
        self.assertIn("tb.clk", wave.signals)

    def test_max_time_truncates(self) -> None:
        wave = read_vcd(GOLDEN, max_time=20)
        self.assertEqual(wave.traces["tb.dut.count"].times, [11, 20])
        self.assertEqual(wave.max_time, 20)


class TestValueNormalisation(unittest.TestCase):
    def test_leading_zeros_are_insignificant(self) -> None:
        self.assertEqual(normalize_value("b00001010"), normalize_value("b1010"))

    def test_z_and_x_keep_width(self) -> None:
        self.assertEqual(normalize_value("bxxxx"), "xxxx")
        self.assertEqual(normalize_value("b000z"), "000z")

    def test_scalars_pass_through(self) -> None:
        self.assertEqual(normalize_value("1"), "1")
        self.assertEqual(normalize_value("X"), "x")

    def test_is_case_insensitive(self) -> None:
        self.assertEqual(normalize_value("B1010"), "1010")


class TestDisplayFormatting(unittest.TestCase):
    """Raw normalised values are right for comparison but wrong for humans."""

    def test_binary_is_padded_back_to_the_declared_width(self) -> None:
        self.assertEqual(format_value("11", 8, "bin"), "00000011")

    def test_hex_and_decimal(self) -> None:
        self.assertEqual(format_value("11", 8, "hex"), "03")
        self.assertEqual(format_value("100", 8, "dec"), "4")
        self.assertEqual(format_value("11111111", 8, "hex"), "ff")

    def test_unknown_bits_are_never_reformatted(self) -> None:
        self.assertEqual(format_value("1x01", 4, "bin"), "1x01")
        self.assertEqual(format_value("x", 1, "hex"), "x")

    def test_unknown_radix_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            format_value("1", 1, "roman")


class TestParserRobustness(unittest.TestCase):
    def _write(self, text: str) -> Path:
        return write_vcd(text)

    def test_multiline_comment_is_ignored(self) -> None:
        path = self._write(
            "$timescale 1ns $end\n"
            "$scope module tb $end\n"
            "$var wire 1 ! clk $end\n"
            "$upscope $end\n"
            "$enddefinitions $end\n"
            "$comment\n"
            "#99 this line looks like a timestamp but is not\n"
            "1 !\n"
            "$end\n"
            "#5\n"
            "1!\n"
        )
        wave = read_vcd(path)
        self.assertEqual(wave.traces["tb.clk"].times, [5])

    def test_repeated_identical_writes_are_coalesced(self) -> None:
        path = self._write(
            "$timescale 1ns $end\n"
            "$scope module tb $end\n"
            "$var wire 1 ! clk $end\n"
            "$upscope $end\n"
            "$enddefinitions $end\n"
            "#5\n1!\n#6\n1!\n#7\n1!\n#8\n0!\n"
        )
        wave = read_vcd(path)
        self.assertEqual(wave.traces["tb.clk"].times, [5, 8])

    def test_missing_file_raises_parse_error(self) -> None:
        with self.assertRaises(VcdParseError):
            read_vcd(Path("definitely-not-here.vcd"))

    def test_bad_regex_raises_parse_error(self) -> None:
        with self.assertRaises(VcdParseError):
            read_vcd(GOLDEN, signals=["[unclosed"])

    def test_vector_on_its_own_line_with_space(self) -> None:
        path = self._write(
            "$timescale 1ns $end\n"
            "$scope module tb $end\n"
            "$var wire 4 # bus [3:0] $end\n"
            "$upscope $end\n"
            "$enddefinitions $end\n"
            "#1\nb1010 #\n"
        )
        wave = read_vcd(path)
        self.assertEqual(wave.traces["tb.bus"].values, ["1010"])


if __name__ == "__main__":
    unittest.main()
