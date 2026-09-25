"""wavediff -- find the first moment two simulation waveforms disagree.

Typical use::

    import wavediff

    a = wavediff.read_vcd("golden.vcd")
    b = wavediff.read_vcd("dut.vcd")
    result = wavediff.diff(a, b)

    if not result.identical:
        print("first difference at", result.first_divergence)
        for sig in result.differing:
            print(" ", sig.name, sig.runs[0].describe_time())
"""

from .align import ALIGNMENT_MODES, Alignment, resolve_alignment
from .diff import DiffResult, DiffRun, SignalDiff, diff_waveforms
from .model import Signal, Trace, Waveform, format_value, normalize_value
from .report import render_html, render_summary_text
from .vcd import VCD_PARSER_BACKEND, VcdParseError, read_vcd

__version__ = "0.1.0"

__all__ = [
    "ALIGNMENT_MODES",
    "Alignment",
    "DiffResult",
    "DiffRun",
    "Signal",
    "SignalDiff",
    "Trace",
    "VCD_PARSER_BACKEND",
    "VcdParseError",
    "Waveform",
    "__version__",
    "diff",
    "diff_waveforms",
    "format_value",
    "normalize_value",
    "read_vcd",
    "render_html",
    "render_summary_text",
    "resolve_alignment",
]


def diff(a: Waveform, b: Waveform, mode: str = "auto", **kwargs) -> DiffResult:
    """Convenience wrapper: resolve alignment and compare in one call."""
    alignment = resolve_alignment(a, b, mode, **kwargs)
    return diff_waveforms(a, b, alignment)
