# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- FST reader (see `docs/roadmap.md`)
- Scope-level summary output (`--summary`)
- `--ignore` signal patterns
- GitHub Action wrapper

## [0.1.0] - 2026-09-20

First release. The whole point is that it answers one question well: *where did
these two waveforms first stop matching?*

### Added

- **Streaming VCD parser** (`wavediff.read_vcd`): single forward pass, no
  retained token tree. Signal-name filtering keeps memory proportional to what
  you asked for rather than what was dumped; `max_time` truncates long dumps.
- **Timeline alignment** with four explicit strategies — `none`, `auto`,
  `shift`, `reference` — and `auto` inferring an offset by majority vote across
  shared signals. Refuses to shift on a tie or on a single supporting signal,
  and always reports the decision in `Alignment.detail`.
- **Transition-stream diff engine**: exact (not sampled) detection of the first
  divergence and of every maximal interval of disagreement, at
  `O(T_a + T_b)` per signal. Distinguishes an interval that closes from one that
  stays open to the end of the dump.
- **Self-contained HTML report**: inline SVG waveforms for each divergent
  signal with the disagreeing intervals shaded, bus values labelled at their
  declared width. No scripts, no network requests — one file works from an
  email attachment or a shared drive.
- **CLI** with a stable CI contract: exit `0` identical, `1` diverged, `2`
  error. Plus `--json` for machine-readable results and `--radix {bin,hex,dec}`
  for display.
- **Zero runtime dependencies.** Pure Python 3.10+, stdlib only.
- 70 unit tests covering the parser, alignment, diff semantics, report
  rendering and CLI exit codes, runnable with stdlib `unittest` — no test
  framework to install.

### Notes

- Known limits, stated up front rather than discovered later: VCD only (no FST
  or GHW), a pure-Python parser, and alignment restricted to a constant offset.
  See `docs/design.md` §8.

[Unreleased]: https://github.com/Sonnet-dawn/wavediff/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Sonnet-dawn/wavediff/releases/tag/v0.1.0
