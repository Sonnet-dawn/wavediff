"""Report rendering tests.

The report is the artefact users actually look at, so its correctness is tested
directly rather than only through end-to-end snapshots.
"""

from __future__ import annotations

import re
import unittest

from wavediff.model import Signal, Trace
from wavediff.report import _scalar_lane, _segments_in_window


def _trace(name: str, width: int, initial: str, pairs: list[tuple[int, str]]) -> Trace:
    return Trace(
        signal=Signal(code="!", name=name, width=width),
        times=[t for t, _ in pairs],
        values=[v for _, v in pairs],
        initial=initial,
    )


def _points(path_d: str) -> list[tuple[float, float]]:
    return [
        (float(x), float(y))
        for x, y in re.findall(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", path_d)
    ]


class TestSegmentsInWindow(unittest.TestCase):
    def test_window_is_clipped_and_values_carried_in(self) -> None:
        trace = _trace("s", 1, "0", [(10, "1"), (20, "0")])
        self.assertEqual(
            _segments_in_window(trace, 5, 25),
            [(5, 10, "0"), (10, 20, "1"), (20, 25, "0")],
        )

    def test_value_at_window_start_comes_from_history(self) -> None:
        trace = _trace("s", 1, "0", [(1, "1")])
        self.assertEqual(_segments_in_window(trace, 50, 60), [(50, 60, "1")])

    def test_degenerate_window_does_not_produce_empty_segments(self) -> None:
        trace = _trace("s", 1, "1", [])
        self.assertTrue(all(end > start for start, end, _ in _segments_in_window(trace, 7, 7)))


class TestScalarLane(unittest.TestCase):
    """A 1-bit trace must render as a connected step waveform."""

    def setUp(self) -> None:
        # Rises at 10, falls at 20, within a 0..30 window.
        self.trace = _trace("tb.valid", 1, "0", [(10, "1"), (20, "0")])
        self.svg = _scalar_lane(self.trace, 0, 30, lambda t: float(t), 0.0, "#000")

    def test_produces_a_single_path(self) -> None:
        self.assertEqual(self.svg.count("<path"), 1)

    def test_contains_vertical_transition_edges(self) -> None:
        """A missing edge renders as disconnected dashes, not a waveform."""
        d = re.search(r'<path d="([^"]*)"', self.svg).group(1)
        points = _points(d)
        verticals = [
            (a, b) for a, b in zip(points, points[1:]) if a[0] == b[0] and a[1] != b[1]
        ]
        self.assertEqual(len(verticals), 2, f"expected 2 edges (rise, fall), got {verticals}")

    def test_edges_sit_at_the_transition_times(self) -> None:
        d = re.search(r'<path d="([^"]*)"', self.svg).group(1)
        points = _points(d)
        vertical_xs = [
            a[0] for a, b in zip(points, points[1:]) if a[0] == b[0] and a[1] != b[1]
        ]
        self.assertEqual(vertical_xs, [10.0, 20.0])

    def test_high_and_low_are_drawn_at_different_heights(self) -> None:
        d = re.search(r'<path d="([^"]*)"', self.svg).group(1)
        ys = {y for _, y in _points(d)}
        self.assertEqual(len(ys), 2, "logic 1 and logic 0 must be distinct levels")

    def test_unknown_bits_get_a_dashed_overlay(self) -> None:
        trace = _trace("tb.x", 1, "x", [(10, "1")])
        svg = _scalar_lane(trace, 0, 20, lambda t: float(t), 0.0, "#000")
        self.assertEqual(svg.count("<path"), 2)
        self.assertIn("stroke-dasharray", svg)

    def test_flat_signal_still_renders_one_line(self) -> None:
        trace = _trace("tb.rst_n", 1, "1", [])
        svg = _scalar_lane(trace, 0, 20, lambda t: float(t), 0.0, "#000")
        d = re.search(r'<path d="([^"]*)"', svg).group(1)
        ys = {y for _, y in _points(d)}
        self.assertEqual(len(ys), 1)


if __name__ == "__main__":
    unittest.main()
