"""Timeline alignment between two waveforms.

This is the part of wavediff that carries the real design weight, so it is
worth stating the problem plainly.

Two VCD dumps of "the same" testbench have no guaranteed common time origin.
A purely combinational fix leaves timestamps comparable, but add a pipeline
stage and every downstream transition in file B happens one cycle later than
in A -- the raw diff is then a wall of noise and the useful signal (one real
functional change) is invisible.

Rather than pick a single clever rule, wavediff exposes explicit strategies and
makes the chosen one auditable in the report:

``none``
    Trust absolute timestamps. Correct whenever both sims share a time origin
    (the common case for a re-run with a small RTL edit).
``shift``
    Apply a caller-supplied constant offset to B.
``reference``
    Offset B so that a named signal's first transition lines up with A's.
``auto``
    Infer an offset by majority vote over all shared signals. Deliberately
    conservative: a single vote is never enough to shift anything.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .model import Waveform

__all__ = ["Alignment", "resolve_alignment", "ALIGNMENT_MODES"]

ALIGNMENT_MODES = ("auto", "none", "shift", "reference")


@dataclass(slots=True)
class Alignment:
    """How B's timestamps map onto A's timeline.

    A transition at time ``t`` in B is compared against time ``t + offset`` in
    A. ``offset == 0`` means absolute timestamps were used unchanged.
    """

    mode: str
    offset: int = 0
    reference: str | None = None
    detail: str = ""

    def describe(self) -> str:
        if self.offset == 0:
            return f"absolute timestamps (mode={self.mode})"
        sign = "+" if self.offset > 0 else ""
        return f"B shifted by {sign}{self.offset} time units (mode={self.mode}, {self.detail})"


def _first_transition(wave: Waveform, name: str) -> int | None:
    trace = wave.traces.get(name)
    if trace is None or trace.is_empty:
        return None
    return trace.times[0]


def resolve_alignment(
    a: Waveform,
    b: Waveform,
    mode: str = "auto",
    *,
    reference: str | None = None,
    shift: int = 0,
    min_votes: int = 2,
) -> Alignment:
    """Build the :class:`Alignment` for comparing ``b`` against ``a``.

    Args:
        mode: One of :data:`ALIGNMENT_MODES`.
        reference: Signal name required by ``mode="reference"``.
        shift: Offset required by ``mode="shift"``.
        min_votes: Minimum number of agreeing signals before ``auto`` will
            apply a non-zero offset.
    """
    if mode not in ALIGNMENT_MODES:
        raise ValueError(f"unknown alignment mode {mode!r}; expected one of {ALIGNMENT_MODES}")

    if mode == "none":
        return Alignment("none", 0, detail="no offset applied")

    if mode == "shift":
        return Alignment("shift", shift, detail=f"user-supplied offset {shift}")

    if mode == "reference":
        if not reference:
            raise ValueError("mode='reference' requires a signal name")
        ta = _first_transition(a, reference)
        tb = _first_transition(b, reference)
        if ta is None or tb is None:
            raise ValueError(
                f"reference signal {reference!r} has no transitions in "
                f"{'A' if ta is None else 'B'}"
            )
        return Alignment("reference", ta - tb, reference=reference, detail=f"aligned on {reference}")

    # ---- auto: majority vote over every shared signal -------------------
    votes: Counter[int] = Counter()
    contributors = 0
    # Sorted so the outcome never depends on set-iteration order.
    for name in sorted(a.traces.keys() & b.traces.keys()):
        ta = _first_transition(a, name)
        tb = _first_transition(b, name)
        if ta is None or tb is None:
            continue
        votes[ta - tb] += 1
        contributors += 1

    if not votes:
        return Alignment("auto", 0, detail="no shared transitions to vote on")

    top = votes.most_common()
    best_count = top[0][1]
    # On a tie, stay put: shifting a timeline is a destructive act, so it needs
    # a clear majority rather than a coin flip.
    winners = [offset for offset, count in top if count == best_count]
    offset = 0 if 0 in winners else min(winners)
    agreeing = votes[offset]

    if offset == 0:
        return Alignment("auto", 0, detail=f"{agreeing}/{contributors} signals already aligned")

    if agreeing < min_votes:
        return Alignment(
            "auto",
            0,
            detail=(
                f"candidate offset {offset} backed by only {agreeing} signal(s), "
                f"below min_votes={min_votes}; left unaligned"
            ),
        )

    return Alignment(
        "auto",
        offset,
        detail=f"{agreeing}/{contributors} shared signals agree on offset {offset}",
    )
