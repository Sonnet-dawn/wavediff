"""Core data structures shared across wavediff.

The model is deliberately small: a parsed VCD becomes a :class:`Waveform`
holding one :class:`Trace` per signal. Everything downstream (alignment,
diffing, reporting) only ever touches these two types.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Sentinel used when comparing transition streams of different lengths.
INF = float("inf")


@dataclass(slots=True)
class Signal:
    """A single declared VCD variable.

    Attributes:
        code: The short VCD identifier code, e.g. ``!`` or ``#a``.
        name: Fully qualified hierarchical name, e.g. ``tb.dut.data``.
        width: Bit width as declared in the ``$var`` statement.
        kind: VCD variable type -- ``wire``, ``reg``, ``integer``, ``real``...
    """

    code: str
    name: str
    width: int = 1
    kind: str = "wire"


@dataclass(slots=True)
class Trace:
    """Value transitions of one signal, ordered by increasing time.

    ``times`` and ``values`` are parallel arrays. The value *before* the first
    transition is held in :attr:`initial`, which VCD parsers conventionally
    report as unknown (``x``) until ``$dumpvars`` runs.
    """

    signal: Signal
    times: list[int] = field(default_factory=list)
    values: list[str] = field(default_factory=list)
    initial: str = "x"

    @property
    def is_empty(self) -> bool:
        return not self.times

    def value_at(self, time: int) -> str:
        """Return the signal value in effect at ``time``.

        Uses binary search so callers can sample arbitrary points without
        scanning the whole trace.
        """
        import bisect

        idx = bisect.bisect_right(self.times, time)
        if idx == 0:
            return self.initial
        return self.values[idx - 1]


@dataclass(slots=True)
class Waveform:
    """A parsed VCD file: signal declarations plus their transition streams."""

    path: str
    timescale: str = "1ns"
    signals: dict[str, Signal] = field(default_factory=dict)
    traces: dict[str, Trace] = field(default_factory=dict)
    end_time: int = 0
    #: Names of declared signals that satisfied the parser's name filter. This
    #: is kept separately from ``traces`` because a filtered signal may be
    #: declared yet never toggle, and it still belongs in the comparison set.
    matched: set[str] = field(default_factory=set)

    def __len__(self) -> int:
        return len(self.traces)

    @property
    def max_time(self) -> int:
        """Last timestamp seen anywhere in the file (in timescale units)."""
        if self.end_time:
            return self.end_time
        return max((t.times[-1] for t in self.traces.values() if t.times), default=0)


def format_value(value: str, width: int = 1, radix: str = "bin") -> str:
    """Render a normalised value the way an engineer reads a waveform.

    Comparison happens on the normalised form (see :func:`normalize_value`),
    which drops insignificant leading zeros. That form is a poor label -- an
    8-bit counter reads ``11`` instead of ``00000011`` -- so display pads the
    value back to its declared width and can convert to hex or decimal.

    Values containing ``x``/``z`` are always shown verbatim: their bit pattern
    *is* the information.
    """
    if not value or set(value) - {"0", "1"}:
        return value
    if radix == "bin":
        return value.zfill(max(width, 1))
    try:
        number = int(value, 2)
    except ValueError:  # pragma: no cover - guarded by the check above
        return value
    if radix == "hex":
        return format(number, f"0{max((width + 3) // 4, 1)}x")
    if radix == "dec":
        return str(number)
    raise ValueError(f"unknown radix {radix!r}; expected bin, hex or dec")


def normalize_value(raw: str) -> str:
    """Canonicalise a VCD value string so equal values compare equal.

    ``b0011`` and ``b11`` are the same number, and VCD dumps are inconsistent
    about zero padding, so binary vectors are stripped of leading zeros.
    Values containing ``x``/``z`` are only lowercased, never trimmed, because
    their width carries meaning.
    """
    v = raw.strip().lower()
    if not v:
        return v
    if v[0] in "bB":
        bits = v[1:]
        if set(bits) <= {"0", "1"}:
            trimmed = bits.lstrip("0")
            return trimmed or "0"
        return bits
    return v
