# Design notes

This document explains the decisions that are not obvious from the code. If you
are considering contributing, or deciding whether to trust the output, read the
alignment section.

## 1. The core problem: no common time origin

A VCD file is a sequence of `(time, value)` events per signal. Two files dumped
from "the same" testbench are **not** guaranteed to describe the same timeline:

| Cause | Effect on timestamps |
|---|---|
| Added pipeline stage | All downstream transitions shift by one clock period |
| Changed clock generator / reset stretch | Global scale or shift changes |
| Different `$dumpvars` start | Different zero point |
| Compiler scheduling | Small, arbitrary shifts |

A naive diff compares raw timestamps. Under any of the above it reports
hundreds of differences when the design changed in exactly one place. The tool
then becomes noise, and a noisy tool gets uninstalled.

So wavediff separates two questions, and never conflates them:

1. **How do the two timelines relate?** → *alignment* (explicit, auditable)
2. **Given that relation, where do values differ?** → *diff*

## 2. Value normalisation

VCD producers disagree about representation:

```
b0011 !          # zero-padded to the declared width
b11 !            # minimal
3!               # not legal for vectors, but appears in the wild
```

`normalize_value` reduces these to a single form so that equality means
*equality of the simulated value*, not of the text. Binary vectors with only
`0`/`1` are stripped of leading zeros. Vectors containing `x` or `z` are
**not** trimmed, because there the bit pattern is the information: `xx` and `x`
are different states of a 2-bit bus.

The normalised form is deliberately not what the user sees. An 8-bit counter
reads `11` in normalised form, which is wrong for a human, so
`format_value` pads back to the declared width and can convert to hex or
decimal at display time. Comparison and presentation are separate concerns.

## 3. Diffing transition streams, not sampled grids

The obvious implementation samples both waveforms on a fixed grid and compares
sample by sample. It is wrong and slow at the same time:

- **Wrong**, because VCD transitions can occur at any time within a step unit,
  so a grid will misreport the exact divergence point — which is the one number
  the tool exists to produce.
- **Slow**, because cost becomes `O(duration / step)` regardless of how few
  transitions actually occurred. A mostly-idle 1 ms dump at 1 ps resolution is
  a billion samples that a transition-based diff handles in a few thousand.

Instead, `_compare_traces` walks the two transition lists with two pointers,
maintaining the current value of each side, and emits **maximal intervals** of
disagreement. Cost is `O(T_a + T_b)` per signal.

Three consequences worth stating:

- A difference that already exists at `t=0` is reported, because the initial
  state is evaluated before any transition is applied.
- A run that never closes has `end = None`, reported as `"30 .. end"`. This
  distinguishes "broken for one cycle" from "broken forever", which is usually
  the first thing you want to know.
- A run that opens and closes at the same timestamp is discarded: no waveform
  viewer could show it, so it is an artefact of the walk, not a difference.

## 4. Alignment

### Model

Alignment reduces to a single integer offset applied to B:

> a transition at time `t` in B is compared against time `t + offset` in A.

Constant offset is a deliberate limitation. It covers pipeline latency and
zero-point differences — the common cases — and it is *explainable*. A general
time-warping model would fit more situations and be impossible to audit, and an
unauditable alignment is worse than none: it silently hides real differences.

### The `auto` vote

`auto` proposes an offset per shared signal and takes a majority:

```
offset_candidate(signal) = first_transition(A, signal) - first_transition(B, signal)
```

A 4-signal waveform where B is uniformly shifted by 10 units → four votes for
`-10` → offset `-10`.

**`t=0` state must not vote.** This is the subtle part. Every VCD writes its
initial state at `t=0` via `$dumpvars`. If those writes counted as transitions,
every signal in every file would have `first_transition == 0`, every candidate
would be `0`, and the vote would conclude "already aligned" for a waveform that
is shifted by 10. The alignment logic would be dead code that always agrees
with itself.

The fix is in the parser, where it belongs: a value in force at `t=0` is stored
as `Trace.initial`, **not** as a transition. Alignment then votes on behavioural
events only. `tests/test_align.py::test_zero_time_state_does_not_dominate_the_vote`
pins this down, because it is exactly the kind of thing a later "cleanup" would
undo.

### Why a vote, and not a single reference signal

A single named reference is fragile: pick a signal that never toggles in one
file and the alignment silently degrades to `0`, which is the noisy outcome we
were avoiding. A vote degrades gracefully — one unusable signal contributes
nothing, and the rest still carry the decision.

### Conservatism

Shifting a timeline is destructive: a wrong offset can turn a real bug into a
clean report. So `auto` refuses to act without evidence:

- **Ties stay put.** If `0` and `-10` tie, the offset is `0`. A coin flip is not
  a basis for rewriting a timeline.
- **`min_votes` (default 2).** A single supporting signal cannot justify a
  shift. The result records *why* in `Alignment.detail`, and the report prints
  it, so a reader can always tell what happened:

  ```
  alignment: B shifted by -10 time units (mode=auto, 4/4 shared signals agree on offset -10)
  alignment: absolute timestamps (mode=auto, candidate offset -7 backed by only 1 signal(s), below min_votes=2; left unaligned)
  ```

- **Deterministic.** Candidate signals are iterated in sorted order, so `auto`
  never depends on `set` iteration order. CI must give the same answer twice.

## 5. Signals present in only one file

A signal that vanishes between two dumps is a regression, not a detail, so it
is reported (`only-in-a` / `only-in-b`) rather than skipped. It is the kind of
thing a "just diff the common signals" implementation silently loses.

## 6. Filtering

`--signals PATTERN` narrows on three levels, and getting this wrong produced a
real bug during development:

1. The parser still reads every line (it must, to stay in sync with the
   stream) but stores transitions only for matching signals. Memory is
   proportional to what you asked for, not to what was dumped.
2. The **comparison set** must narrow too. If the filter only affected storage,
   a filter matching nothing would compare all declared signals and report a
   confident "identical" — a false pass in CI. Hence `Waveform.matched` and the
   `only_signals is not None` check (an empty list means "nothing matched",
   which must stay distinguishable from "no filter given").
3. The CLI treats an empty comparison set as an error (exit `2`), because
   "nothing to compare" is never what the user meant.

## 7. Complexity

| Stage | Cost |
|---|---|
| Parse | `O(lines)` single forward pass, `O(retained signals × transitions)` memory |
| Alignment | `O(shared signals)` |
| Diff | `O(Σ (T_a + T_b))` over compared signals |
| Report | `O(differing signals × runs)` |

No stage is superlinear in file size, and the diff cost is bounded by the
number of *events*, not the duration of the simulation.

## 8. Known limitations

- **VCD only.** FST and GHW are not implemented; FSDB is proprietary.
- **Pure Python parser.** A single pass is fast for typical testbench dumps,
  but tens of GB will want the native backend in `roadmap.md`. The parser is
  already a single function behind one entry point (`read_vcd`), so a compiled
  backend can replace it without touching alignment, diffing or reporting.
- **No hierarchical rollup.** Comparing a parent scope's aggregate is left to
  the caller via `--signals`.
- **Constant offset only.** See §4.
