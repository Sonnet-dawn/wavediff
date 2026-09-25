"""Signal-level waveform diffing.

The core loop walks two transition streams in lockstep and records maximal
intervals during which the two signals disagree. Working on transitions rather
than on a sampled grid means the answer is exact at arbitrary timescale
resolution, and the cost is O(transitions) instead of O(duration / step).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .align import Alignment
from .model import INF, Trace, Waveform

__all__ = ["DiffRun", "SignalDiff", "DiffResult", "diff_waveforms"]

MATCH = "match"
DIFFER = "differ"
ONLY_A = "only-in-a"
ONLY_B = "only-in-b"


@dataclass(slots=True)
class DiffRun:
    """A maximal interval over which two versions of a signal disagree.

    ``end is None`` means the disagreement was still open when one of the
    streams ran out of transitions -- i.e. right up to the end of the dump.
    Times are expressed in A's timeline.
    """

    signal: str
    width: int
    start: int
    end: int | None
    value_a: str
    value_b: str

    @property
    def duration(self) -> int | None:
        return None if self.end is None else self.end - self.start

    def describe_time(self) -> str:
        if self.end is None:
            return f"{self.start} .. end"
        return f"{self.start} .. {self.end}"


@dataclass(slots=True)
class SignalDiff:
    """Diff verdict for one signal name."""

    name: str
    width: int
    status: str
    runs: list[DiffRun] = field(default_factory=list)

    @property
    def first_divergence(self) -> int | None:
        return self.runs[0].start if self.runs else None

    @property
    def differs(self) -> bool:
        return self.status in (DIFFER, ONLY_A, ONLY_B)


@dataclass(slots=True)
class DiffResult:
    """Complete outcome of comparing two waveforms."""

    alignment: Alignment
    signals: list[SignalDiff] = field(default_factory=list)
    timescale: str = "1ns"
    a_end: int = 0
    b_end: int = 0
    # Retained so the HTML report can draw waveforms without re-parsing.
    a_traces: dict[str, Trace] = field(default_factory=dict)
    b_traces: dict[str, Trace] = field(default_factory=dict)

    @property
    def differing(self) -> list[SignalDiff]:
        return [s for s in self.signals if s.differs]

    @property
    def matching(self) -> list[SignalDiff]:
        return [s for s in self.signals if not s.differs]

    @property
    def first_divergence(self) -> int | None:
        times = [s.first_divergence for s in self.signals if s.first_divergence is not None]
        return min(times) if times else None

    @property
    def identical(self) -> bool:
        return not self.differing

    def counts(self) -> dict[str, int]:
        out = {MATCH: 0, DIFFER: 0, ONLY_A: 0, ONLY_B: 0}
        for sig in self.signals:
            out[sig.status] += 1
        return out


def _compare_traces(
    trace_a: Trace,
    trace_b: Trace,
    offset: int,
    name: str,
    width: int,
    limit: int | None = None,
) -> list[DiffRun]:
    """Return every interval where ``trace_a`` and ``trace_b`` disagree.

    ``trace_b`` timestamps are shifted by ``offset`` before comparison.
    """
    runs: list[DiffRun] = []
    times_a, values_a = trace_a.times, trace_a.values
    times_b, values_b = trace_b.times, trace_b.values

    i = j = 0
    len_a, len_b = len(times_a), len(times_b)
    cur_a: str = trace_a.initial
    cur_b: str = trace_b.initial

    open_run: DiffRun | None = None

    def close_run(end: int | None) -> None:
        nonlocal open_run
        if open_run is not None:
            open_run.end = end
            # A disagreement that opens and closes at the same timestamp is
            # not observable on any waveform, so it is not a difference.
            if end is None or end > open_run.start:
                runs.append(open_run)
            open_run = None

    def consider(time: int) -> None:
        """Update run state given both signals' values at ``time``."""
        nonlocal open_run
        if cur_a == cur_b:
            close_run(time)
            return
        if open_run is None:
            open_run = DiffRun(
                signal=name,
                width=width,
                start=time,
                end=None,
                value_a=cur_a,
                value_b=cur_b,
            )

    # Establish the initial state at t=0 before walking transitions, so a
    # difference that already exists at time zero is reported.
    consider(0)

    while i < len_a or j < len_b:
        next_a = times_a[i] if i < len_a else INF
        next_b = (times_b[j] + offset) if j < len_b else INF
        time = next_a if next_a <= next_b else next_b
        if time == INF:
            break
        if limit is not None and time > limit:
            break

        if next_a == time:
            cur_a = values_a[i]
            i += 1
        if next_b == time:
            cur_b = values_b[j]
            j += 1
        consider(time)

    close_run(None)
    return runs


def diff_waveforms(
    a: Waveform,
    b: Waveform,
    alignment: Alignment,
    *,
    only_signals: list[str] | None = None,
    limit: int | None = None,
) -> DiffResult:
    """Compare ``b`` against ``a`` under ``alignment``.

    Signals present in only one file are reported rather than silently ignored,
    since a signal vanishing between two dumps is exactly the kind of
    regression this tool exists to surface.
    """
    result = DiffResult(
        alignment=alignment,
        timescale=a.timescale or b.timescale,
        a_end=a.max_time,
        b_end=b.max_time + alignment.offset,
        a_traces=a.traces,
        b_traces=b.traces,
    )

    names = sorted(set(a.signals) | set(b.signals))
    if only_signals is not None:
        # An empty selection is meaningful: it means "nothing matched", which
        # the caller must be able to distinguish from "no filter given".
        allowed = set(only_signals)
        names = [n for n in names if n in allowed]

    for name in names:
        sig_a = a.signals.get(name)
        sig_b = b.signals.get(name)
        width = (sig_a or sig_b).width  # type: ignore[union-attr]

        if sig_a is None:
            result.signals.append(SignalDiff(name, width, ONLY_B))
            continue
        if sig_b is None:
            result.signals.append(SignalDiff(name, width, ONLY_A))
            continue

        trace_a = a.traces.get(name) or Trace(signal=sig_a)
        trace_b = b.traces.get(name) or Trace(signal=sig_b)

        runs = _compare_traces(trace_a, trace_b, alignment.offset, name, width, limit)
        status = DIFFER if runs else MATCH
        result.signals.append(SignalDiff(name, width, status, runs))

    return result
