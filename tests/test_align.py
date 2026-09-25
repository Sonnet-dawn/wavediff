"""Alignment strategy tests.

These pin down the behaviour that makes wavediff usable on waveforms whose
timelines are not directly comparable -- the whole reason the tool exists.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from wavediff import ALIGNMENT_MODES, read_vcd, resolve_alignment

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "golden.vcd"
DIVERGED = FIXTURES / "diverged.vcd"
SHIFTED = FIXTURES / "shifted.vcd"


class TestAutoAlignment(unittest.TestCase):
    def test_detects_a_uniform_time_shift(self) -> None:
        a, b = read_vcd(GOLDEN), read_vcd(SHIFTED)
        alignment = resolve_alignment(a, b, "auto")
        self.assertEqual(alignment.offset, -10)
        self.assertIn("shared signals agree", alignment.detail)

    def test_leaves_aligned_waveforms_untouched(self) -> None:
        a = read_vcd(GOLDEN)
        self.assertEqual(resolve_alignment(a, a, "auto").offset, 0)

    def test_zero_time_state_does_not_dominate_the_vote(self) -> None:
        """t=0 dumpvars state is structural and must not outvote behaviour.

        Every VCD writes its initial state at t=0, so if that counted as a
        transition each file would vote "already aligned" and a genuinely
        shifted waveform would never be realigned.
        """
        a, b = read_vcd(GOLDEN), read_vcd(SHIFTED)
        self.assertEqual(resolve_alignment(a, b, "auto").offset, -10)


class TestExplicitStrategies(unittest.TestCase):
    def test_none_uses_absolute_time(self) -> None:
        a, b = read_vcd(GOLDEN), read_vcd(SHIFTED)
        self.assertEqual(resolve_alignment(a, b, "none").offset, 0)

    def test_shift_applies_a_user_offset(self) -> None:
        a, b = read_vcd(GOLDEN), read_vcd(SHIFTED)
        self.assertEqual(resolve_alignment(a, b, "shift", shift=-10).offset, -10)

    def test_reference_aligns_on_a_named_signal(self) -> None:
        a, b = read_vcd(GOLDEN), read_vcd(SHIFTED)
        alignment = resolve_alignment(a, b, "reference", reference="tb.clk")
        self.assertEqual(alignment.offset, -10)
        self.assertEqual(alignment.reference, "tb.clk")

    def test_reference_requires_a_signal(self) -> None:
        a = read_vcd(GOLDEN)
        with self.assertRaises(ValueError):
            resolve_alignment(a, a, "reference")

    def test_reference_rejects_a_signal_with_no_transitions_in_one_file(self) -> None:
        a, b = read_vcd(GOLDEN), read_vcd(DIVERGED)
        b.traces.pop("tb.clk", None)
        with self.assertRaises(ValueError):
            resolve_alignment(a, b, "reference", reference="tb.clk")

    def test_unknown_mode_is_rejected(self) -> None:
        a = read_vcd(GOLDEN)
        with self.assertRaises(ValueError):
            resolve_alignment(a, a, "mind-meld")


class TestAutoAlignmentDoesNotOverreach(unittest.TestCase):
    def test_a_single_supporting_signal_is_not_enough_to_shift(self) -> None:
        a, b = read_vcd(GOLDEN), read_vcd(DIVERGED)
        # Only one signal has a usable transition stream in each file.
        b.traces = {"tb.clk": b.traces["tb.clk"]}
        b.traces["tb.clk"].times = [t + 7 for t in b.traces["tb.clk"].times]
        alignment = resolve_alignment(a, b, "auto", min_votes=2)
        self.assertEqual(alignment.offset, 0)
        self.assertIn("min_votes", alignment.detail)


class TestModeListIsStable(unittest.TestCase):
    def test_all_documented_modes_are_accepted(self) -> None:
        a = read_vcd(GOLDEN)
        for mode in ALIGNMENT_MODES:
            if mode == "reference":
                resolve_alignment(a, a, mode, reference="tb.clk")
            else:
                resolve_alignment(a, a, mode)


if __name__ == "__main__":
    unittest.main()
