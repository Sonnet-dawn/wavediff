# Roadmap

Ordered by *usefulness per unit of effort*, not by how impressive it sounds.
Items marked 💬 have an open design question worth discussing — please open an
issue rather than sending a large PR.

## v0.2 — make it fit real regression flows

- [ ] **FST reader.** FST is what `$dumpfile("x.fst")` produces and is far more
      common than VCD in modern flows, at a fraction of the size. Format
      reference is public (GTKWave's `fstapi`). Highest-value single feature.
- [ ] **Scope-level summary.** `--summary` that reports "3 signals diverged
      under `tb.dut.alu`" instead of listing 400 signals, so a large design is
      readable at a glance.
- [ ] **`--ignore` patterns.** `--ignore '^tb\.dut\.debug_.*'` to exclude
      signals that are known-unstable, without having to enumerate the ones you
      want.
- [ ] **GitHub Action wrapper.** `uses: Sonnet-dawn/wavediff@v1` producing the report
      as a job summary, so the diff shows up without downloading an artefact.

## v0.3 — performance

- [ ] **Native parser behind the existing interface.** The parser is one
      function (`read_vcd`) with a plain data model, so a Rust or C++
      implementation can drop in behind it with no change to alignment,
      diffing or reporting. Target: multi-GB dumps at interactive speed, memory
      mapped, with the pure-Python path retained as the reference
      implementation and the fallback.
- [ ] **Streaming diff.** Today both waveforms are held in memory. A streaming
      merge that never materialises a full trace would remove the last
      file-size ceiling.
- [ ] 💬 **Parallel signal comparison.** The diff is embarrassingly parallel
      across signals; the open question is whether thread overhead beats the
      work for small waveforms, and whether to use `multiprocessing` (no GIL
      contention, high startup cost) or a native core.

## v0.4 — deeper verification features

- [ ] 💬 **Clock-aware alignment.** Infer the clock period and express the
      offset in *cycles* rather than raw time units. Much more meaningful to an
      engineer ("B is 3 cycles late"), but it needs a reliable clock detector
      and a clear rule for multi-clock designs.
- [ ] 💬 **Write-back / regress detection.** Distinguish "B diverges" from "B
      diverges and then feeds back into a control signal", which is the
      difference between a local bug and a design-wide one.
- [ ] **Export to CSV / Parquet** for downstream analysis in pandas.
- [ ] **Interactive HTML.** Zoom and pan in the report. Deliberately deferred:
      the current report is a single static file with no scripts, which works
      from an email attachment. Interactivity costs that property, so it should
      be additive (progressive enhancement) rather than a rewrite.

## Explicitly out of scope

- **A waveform viewer.** GTKWave, Surfer and friends do that well. wavediff
  produces a *diff report* and should stay focused on that.
- **FSDB.** Proprietary; there is no legal reader.
- **Replacing Verdi for sign-off.** This is a fast, free, CI-friendly first
  pass, not a sign-off tool.

## How to help

The two most valuable contributions, both small:

1. **A VCD file that breaks the parser.** Real-world dumps use every corner of
   the format. Send the file (or a minimised version) and it becomes a
   `tests/fixtures/` case.
2. **A waveform pair where `auto` picks the wrong offset.** These are the
   hardest bugs and the most interesting. Include what the correct offset is
   and why, and it becomes an alignment regression test.
