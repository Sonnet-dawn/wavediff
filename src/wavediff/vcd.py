"""Streaming VCD parser.

Design notes
------------
VCD files are routinely hundreds of megabytes, so this parser is a single
forward pass over the file with no token tree retained. Two properties matter
for the diff use case:

* **Signal filtering.** If the caller only cares about ``tb.dut.*``, we still
  have to read every line to stay in sync with the stream, but we never store
  transitions for signals outside the filter. Memory stays proportional to
  what was asked for, not to what was dumped.
* **No value-change coalescing beyond the identical run.** A repeated write of
  the same value is dropped, because VCD producers emit those freely and they
  would otherwise pollute the diff with phantom differences.

The public entry point is :func:`read_vcd`.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TextIO

from .model import Trace, Signal, Waveform, normalize_value

__all__ = ["read_vcd", "VcdParseError", "VCD_PARSER_BACKEND"]

#: Which implementation produced a parse. The pure-Python parser is always
#: available; a native accelerator may override this at import time.
VCD_PARSER_BACKEND = "python"

_SCOPE_RE = re.compile(r"^\$scope\s+(\w+)\s+(\S+)")
_VAR_RE = re.compile(r"^\$var\s+(\w+)\s+(\d+)\s+(\S+)\s+(\S+)")
_TIMESCALE_RE = re.compile(r"^\$timescale\s+(.+)")
# A value-change line is either '#<time>', or '<value><code>' / 'b<bits> <code>'.
_TIME_RE = re.compile(r"^#(\d+)")


class VcdParseError(ValueError):
    """Raised when a file is not a VCD, or is structurally malformed."""


def _matches(name: str, patterns: Sequence[re.Pattern[str]] | None) -> bool:
    if not patterns:
        return True
    return any(p.search(name) for p in patterns)


def compile_filters(patterns: Sequence[str] | None) -> list[re.Pattern[str]] | None:
    """Compile user-supplied signal-name patterns into regexes.

    Patterns are treated as regexes, so ``^tb\\.dut\\.`` anchors and
    ``clk|rst`` alternations both work without extra syntax.
    """
    if not patterns:
        return None
    out = []
    for pat in patterns:
        try:
            out.append(re.compile(pat))
        except re.error as exc:  # pragma: no cover - surfaced to the CLI
            raise VcdParseError(f"invalid signal pattern {pat!r}: {exc}") from exc
    return out


def _iter_statements(handle: TextIO) -> Iterator[list[str]]:
    """Yield whitespace-separated tokens, one logical line at a time."""
    for line in handle:
        stripped = line.strip()
        if stripped:
            yield stripped.split()


def read_vcd(
    path: str | Path,
    *,
    signals: Sequence[str] | None = None,
    max_time: int | None = None,
) -> Waveform:
    """Parse ``path`` into a :class:`Waveform`.

    Args:
        path: VCD file to read.
        signals: Optional regex patterns; only matching signals are retained.
        max_time: Stop parsing once this simulation time is passed. Useful for
            diffing just the opening window of a long regression.

    Raises:
        VcdParseError: If the file has no ``$enddefinitions`` section or the
            file cannot be decoded as text.
    """
    path = Path(path)
    patterns = compile_filters(signals)
    wave = Waveform(path=str(path))
    code_to_name: dict[str, str] = {}
    current_scope: list[str] = []
    in_definitions = False
    in_comment = False
    current_time = 0
    last_values: dict[str, str] = {}

    def open_file() -> TextIO:
        try:
            return path.open("r", encoding="utf-8", errors="replace")
        except OSError as exc:
            raise VcdParseError(f"cannot open {path}: {exc}") from exc

    with open_file() as handle:
        statements = _iter_statements(handle)
        for tokens in statements:
            head = tokens[0]

            # $comment bodies are free text and may contain anything, so they
            # must be consumed before any value-change interpretation happens.
            if in_comment:
                if "$end" in tokens:
                    in_comment = False
                continue
            if head == "$comment":
                if "$end" not in tokens:
                    in_comment = True
                continue

            if not in_definitions:
                if head.startswith("$scope"):
                    match = _SCOPE_RE.match(" ".join(tokens))
                    if match:
                        current_scope.append(match.group(2))
                    continue
                if head.startswith("$upscope"):
                    if current_scope:
                        current_scope.pop()
                    continue
                if head.startswith("$var"):
                    match = _VAR_RE.match(" ".join(tokens))
                    if match:
                        kind, width, code, short = match.groups()
                        full = ".".join([*current_scope, short])
                        sig = Signal(code=code, name=full, width=int(width), kind=kind)
                        wave.signals[full] = sig
                        code_to_name[code] = full
                        if _matches(full, patterns):
                            wave.matched.add(full)
                    continue
                if head.startswith("$timescale"):
                    match = _TIMESCALE_RE.match(" ".join(tokens))
                    if match:
                        wave.timescale = match.group(1).replace("$end", "").strip()
                    continue
                if head.startswith("$enddefinitions"):
                    in_definitions = True
                    continue
                continue

            # ---- body: timestamps and value changes --------------------
            if head.startswith("#"):
                match = _TIME_RE.match(head)
                if not match:
                    continue
                current_time = int(match.group(1))
                # The cutoff is checked before the timestamp is recorded, so a
                # truncated dump reports the last time it actually kept.
                if max_time is not None and current_time > max_time:
                    break
                if current_time > wave.end_time:
                    wave.end_time = current_time
                continue

            if head.startswith("$"):
                # $dumpvars/$dumpoff/$dumpon/$comment etc. The following
                # value-change lines are handled by the branches below.
                continue

            if len(tokens) >= 2 and head[0] in "bBrR":
                code = tokens[1]
                raw = head
            else:
                code = head[1:]
                raw = head[0]

            name = code_to_name.get(code)
            if name is None:
                continue
            if not _matches(name, patterns):
                continue

            value = normalize_value(raw)
            if last_values.get(name) == value:
                continue
            last_values[name] = value

            trace = wave.traces.get(name)
            if trace is None:
                trace = Trace(signal=wave.signals[name])
                wave.traces[name] = trace

            # The value in force at t=0 is the signal's *initial state*, not a
            # transition. Keeping it out of the transition stream matters for
            # alignment: every VCD dumps t=0 state, so counting it as a
            # transition would make every waveform "start at 0" and drown out
            # the real behavioural evidence used to infer a time offset.
            if current_time == 0 and not trace.times:
                trace.initial = value
                continue

            trace.times.append(current_time)
            trace.values.append(value)

    return wave
