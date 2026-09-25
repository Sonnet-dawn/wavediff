"""Command-line interface.

Exit codes are a stable contract, because the primary use case is CI:

===  ==================================================
0    waveforms are identical under the chosen alignment
1    at least one signal diverged (or exists in only one file)
2    the comparison could not be performed (bad file, bad option)
===  ==================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .align import ALIGNMENT_MODES, resolve_alignment
from .diff import DiffResult, diff_waveforms
from .report import render_html, render_summary_text
from .vcd import VcdParseError, read_vcd

__all__ = ["main", "build_parser"]

EXIT_IDENTICAL = 0
EXIT_DIVERGED = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wavediff",
        description="Find the first moment two simulation waveforms disagree.",
        epilog=(
            "Exit codes: 0 identical, 1 diverged, 2 error. "
            "Example: wavediff golden.vcd dut.vcd --align auto --html diff.html"
        ),
    )
    parser.add_argument("a", type=Path, help="reference waveform (A), usually the golden dump")
    parser.add_argument("b", type=Path, help="waveform to check (B), usually the new dump")

    view = parser.add_argument_group("what to compare")
    view.add_argument(
        "-s",
        "--signals",
        action="append",
        metavar="REGEX",
        help="only compare signals whose full name matches this regex (repeatable)",
    )
    view.add_argument(
        "--until",
        type=int,
        metavar="TIME",
        help="ignore everything after this simulation time",
    )

    al = parser.add_argument_group("timeline alignment")
    al.add_argument(
        "--align",
        choices=ALIGNMENT_MODES,
        default="auto",
        help="how to line B's timeline up with A's (default: auto)",
    )
    al.add_argument("--shift", type=int, default=0, help="offset added to B, with --align shift")
    al.add_argument("--reference", metavar="SIGNAL", help="signal to align on, with --align reference")

    out = parser.add_argument_group("output")
    out.add_argument("--html", type=Path, metavar="PATH", help="write a standalone HTML report")
    out.add_argument("--json", type=Path, metavar="PATH", help="write a machine-readable JSON result")
    out.add_argument(
        "--radix",
        choices=("bin", "hex", "dec"),
        default="bin",
        help="how bus values are displayed in reports (default: bin)",
    )
    out.add_argument("-q", "--quiet", action="store_true", help="suppress the text summary")
    out.add_argument(
        "--exit-zero",
        action="store_true",
        help="always exit 0 when the comparison succeeded, even if signals differ",
    )
    return parser


def _result_to_dict(result: DiffResult, *, a_path: str, b_path: str) -> dict:
    counts = result.counts()
    return {
        "a": a_path,
        "b": b_path,
        "timescale": result.timescale,
        "alignment": {
            "mode": result.alignment.mode,
            "offset": result.alignment.offset,
            "reference": result.alignment.reference,
            "detail": result.alignment.detail,
        },
        "identical": result.identical,
        "first_divergence": result.first_divergence,
        "counts": counts,
        "signals": [
            {
                "name": sig.name,
                "width": sig.width,
                "status": sig.status,
                "first_divergence": sig.first_divergence,
                "intervals": [
                    {
                        "start": run.start,
                        "end": run.end,
                        "value_a": run.value_a,
                        "value_b": run.value_b,
                    }
                    for run in sig.runs
                ],
            }
            for sig in result.signals
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        wave_a = read_vcd(args.a, signals=args.signals, max_time=args.until)
        wave_b = read_vcd(args.b, signals=args.signals, max_time=args.until)
    except VcdParseError as exc:
        print(f"wavediff: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        alignment = resolve_alignment(
            wave_a,
            wave_b,
            args.align,
            reference=args.reference,
            shift=args.shift,
        )
    except ValueError as exc:
        print(f"wavediff: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    # A --signals filter must also narrow the *comparison set*, not just what
    # the parser stores; otherwise filtering everything out would silently
    # compare all declared signals and report a misleading "identical".
    only = None
    if args.signals:
        only = sorted(wave_a.matched | wave_b.matched)

    result = diff_waveforms(wave_a, wave_b, alignment, only_signals=only, limit=args.until)

    if not result.signals:
        print(
            "wavediff: error: no signals to compare; check --signals patterns",
            file=sys.stderr,
        )
        return EXIT_ERROR

    if not args.quiet:
        print(
            render_summary_text(
                result, a_path=str(args.a), b_path=str(args.b), radix=args.radix
            )
        )

    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(
            render_html(
                result, a_path=str(args.a), b_path=str(args.b), radix=args.radix
            ),
            encoding="utf-8",
        )
        if not args.quiet:
            print(f"\nHTML report written to {args.html}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = _result_to_dict(result, a_path=str(args.a), b_path=str(args.b))
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if not args.quiet:
            print(f"JSON result written to {args.json}")

    if result.identical or args.exit_zero:
        return EXIT_IDENTICAL
    return EXIT_DIVERGED


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
