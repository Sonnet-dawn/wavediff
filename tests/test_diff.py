"""Diff engine and alignment tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from wavediff import diff_waveforms, read_vcd, resolve_alignment
from wavediff.diff import DIFFER, MATCH, ONLY_B

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "golden.vcd"
DIVERGED = FIXTURES / "diverged.vcd"
SHIFTED = FIXTURES / "shifted.vcd"
RECODED = FIXTURES / "recoded.vcd"
EXTRA_SIGNAL = FIXTURES / "extra_signal.vcd"


class TestIdenticalWaveforms(unittest.TestCase):
    def test_a_file_matches_itself(self) -> None:
        wave = read_vcd(GOLDEN)
        result = diff_waveforms(wave, wave, resolve_alignment(wave, wave, "none"))
        self.assertTrue(result.identical)
        self.assertIsNone(result.first_divergence)

    def test_variable_id_codes_do_not_affect_the_verdict(self) -> None:
        """Two simulators assign different id codes to the same waveform."""
        a, b = read_vcd(GOLDEN), read_vcd(RECODED)
        result = diff_waveforms(a, b, resolve_alignment(a, b, "auto"))
        self.assertTrue(result.identical, [s.name for s in result.differing])


class TestDivergenceDetection(unittest.TestCase):
    def setUp(self) -> None:
        self.a, self.b = read_vcd(GOLDEN), read_vcd(DIVERGED)
        self.result = diff_waveforms(self.a, self.b, resolve_alignment(self.a, self.b, "none"))

    def test_first_divergence_time(self) -> None:
        self.assertEqual(self.result.first_divergence, 30)

    def test_only_the_broken_signal_differs(self) -> None:
        names = [s.name for s in self.result.differing]
        self.assertEqual(names, ["tb.dut.count"])

    def test_untouched_signals_match(self) -> None:
        statuses = {s.name: s.status for s in self.result.signals}
        self.assertEqual(statuses["tb.clk"], MATCH)
        self.assertEqual(statuses["tb.rst_n"], MATCH)
        self.assertEqual(statuses["tb.dut.valid"], MATCH)

    def test_divergence_is_bounded_by_reconvergence(self) -> None:
        """The counter is wrong for exactly one interval, then re-converges."""
        run = self.result.differing[0].runs[0]
        self.assertEqual((run.start, run.end), (30, 40))
        # Normalised binary: 0b11 vs 0b111.
        self.assertEqual(run.value_a, "11")
        self.assertEqual(run.value_b, "111")
        self.assertEqual(run.duration, 10)

    def test_counts_add_up(self) -> None:
        counts = self.result.counts()
        self.assertEqual(counts[DIFFER], 1)
        self.assertEqual(counts[MATCH], 3)


class TestUnboundedDivergence(unittest.TestCase):
    def test_a_run_left_open_has_no_end(self) -> None:
        a = read_vcd(GOLDEN)
        b = read_vcd(DIVERGED)
        # Truncate B at the moment it goes wrong: the difference never closes.
        b.traces["tb.dut.count"].times = [11, 20, 30]
        b.traces["tb.dut.count"].values = ["1", "10", "111"]
        result = diff_waveforms(a, b, resolve_alignment(a, b, "none"))
        run = result.differing[0].runs[0]
        self.assertEqual(run.start, 30)
        self.assertIsNone(run.end)
        self.assertEqual(run.describe_time(), "30 .. end")


class TestSignalsOnlyInOneFile(unittest.TestCase):
    def test_extra_signal_in_b_is_reported(self) -> None:
        a, b = read_vcd(GOLDEN), read_vcd(EXTRA_SIGNAL)
        result = diff_waveforms(a, b, resolve_alignment(a, b, "none"))
        statuses = {s.name: s.status for s in result.signals}
        self.assertEqual(statuses["tb.dut.debug"], ONLY_B)
        self.assertFalse(result.identical)

    def test_direction_of_the_extra_signal_is_symmetric(self) -> None:
        from wavediff.diff import ONLY_A

        a, b = read_vcd(EXTRA_SIGNAL), read_vcd(GOLDEN)
        result = diff_waveforms(a, b, resolve_alignment(a, b, "none"))
        statuses = {s.name: s.status for s in result.signals}
        self.assertEqual(statuses["tb.dut.debug"], ONLY_A)


class TestSignalFilteringInDiff(unittest.TestCase):
    def test_only_signals_restricts_the_comparison(self) -> None:
        a, b = read_vcd(GOLDEN), read_vcd(DIVERGED)
        result = diff_waveforms(
            a, b, resolve_alignment(a, b, "none"), only_signals=["tb.clk"]
        )
        self.assertEqual([s.name for s in result.signals], ["tb.clk"])
        self.assertTrue(result.identical)


class TestLimit(unittest.TestCase):
    def test_limit_hides_differences_after_the_cutoff(self) -> None:
        a, b = read_vcd(GOLDEN), read_vcd(DIVERGED)
        result = diff_waveforms(a, b, resolve_alignment(a, b, "none"), limit=25)
        self.assertTrue(result.identical, "difference at t=30 should be past the limit")


if __name__ == "__main__":
    unittest.main()
