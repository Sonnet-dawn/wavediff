# Publishing checklist

The code is the easy half. A repo with no audience gets no stars no matter how
good it is, so this is the sequence to follow *on launch day*. Work through it
in order — the first four items are worth ten times the rest.

## 0. Before anything else: prove it runs

```bash
cd wavediff
PYTHONPATH=src python -m unittest discover -s tests -t tests -v   # expect: OK
PYTHONPATH=src python -m wavediff tests/fixtures/golden.vcd tests/fixtures/diverged.vcd --html /tmp/diff.html
# expect: DIVERGED at t=30, exit code 1
```

Do not publish until both of these are clean on a fresh machine.

## 1. Ownership placeholders

**Status: already done for this repository.** It is published at
[github.com/Sonnet-dawn/wavediff](https://github.com/Sonnet-dawn/wavediff), and
every ownership reference points there.

If you are reusing this scaffold for a fork or a different project, the
mechanism is: the template ships the literal token `OWNER` wherever an
account name belongs, and publishing replaces it. A stale `OWNER` makes badges
and links 404, which is the single most common way a good project looks
abandoned on first contact.

```bash
# Any hit here means an ownership reference was missed. This file is excluded
# because it discusses the placeholder by name.
grep -rn "OWNER" --include="*.md" --include="*.toml" --include="*.yml" . \
  | grep -v "docs/PUBLISHING.md"
```

Files that carry an ownership reference: `README.md`, `README.zh-CN.md`,
`pyproject.toml`, `CHANGELOG.md`, `docs/roadmap.md`,
`.github/workflows/ci.yml`.

## 2. Check the screenshot

`docs/demo.png` is already committed and wired into the README, so the first
screen works out of the box. Look at it before you publish:

- If the waveform panels look wrong, regenerate with
  `PYTHONPATH=src python -m wavediff examples/golden.vcd examples/regressed.vcd --html docs/demo.html`
  and re-screenshot.
- **This asset is the highest-leverage 10 minutes in the launch.** A stranger
  decides whether to care in about three seconds, and a picture of two
  waveforms with one bus clearly wrong is instantly legible to exactly the
  audience you want.

A terminal GIF of the command running is a good second asset. Keep both under
~1 MB and reference them with relative paths so they also render on PyPI.

## 3. Set the repo metadata — it is SEO, not decoration

- **About (description)**: `Find the first moment two simulation waveforms disagree. VCD diff for Verilog/SystemVerilog regression.` — the first sentence is what search engines and GitHub search index.
- **Topics**: `vcd`, `waveform`, `verilog`, `systemverilog`, `eda`, `verification`, `simulation`, `chip-design`, `rtl`, `diff`, `ci`
- **Website**: your `docs/` GitHub Pages URL once enabled.
- Tick **Releases → v0.1.0** and paste the `CHANGELOG.md` section. A release with notes reads as "maintained"; an empty repo with no tags reads as "abandoned experiment".
- Enable **Discussions** if you want design questions (§ the roadmap's 💬 items) to have somewhere to land.

### Publish to PyPI

**Status: deliberately deferred.** GitHub Pages serves the landing page at
`https://sonnet-dawn.github.io/wavediff/`, and the README installs from GitHub:

```bash
pip install git+https://github.com/Sonnet-dawn/wavediff
```

That works today and is verified end to end (install, console script, and all
four exit codes). Deferring PyPI costs little for an EDA tool, because the
audience all have `git` — which is the only extra requirement `git+https`
imposes over a plain `pip install`.

**The one rule while PyPI is deferred:** do not write `pip install wavediff`
anywhere. `wavediff` is currently an **unclaimed name on PyPI**, so that command
does not fail — it installs whatever a stranger publishes. If someone claims the
name and ships something malicious, every reader who follows that instruction
gets it. Advertising an unclaimed package name is a supply-chain invitation, not
just a broken link.

If you want the short command eventually, `.github/workflows/publish.yml` is
already wired for **Trusted Publishing** — no API token is stored anywhere.
It needs two things:

1. A verified PyPI account email. PyPI blocks all account actions (creating
   projects, adding publishers, uploading) until the primary email is verified.
   University mail domains often drop or delay mail from outside the country, so
   if the verification mail never arrives, add a mainstream personal address at
   **https://pypi.org/manage/account/** and set it as primary — adding a new
   address is allowed even while the old one is unverified.
2. A pending publisher at **Account → Publishing → Add a pending publisher**:

   | Field | Value |
   |---|---|
   | PyPI project name | `wavediff` |
   | Owner | `Sonnet-dawn` |
   | Repository name | `wavediff` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

Then run **Actions → publish → Run workflow** and type `publish` in the confirm
field. The workflow runs the tests and the CLI exit-code contract, builds the
sdist and wheel, runs `twine check`, installs the wheel into a fresh venv and
smoke-tests it, and only then uploads.

Finally, flip both READMEs back to `pip install wavediff` (search for the
`FLIP ME` comment) and confirm from a clean environment.

**Until PyPI is claimed, tag pushes do not publish.** The workflow also triggers
on `v*` tags; without a pending publisher configured that job fails at the
upload step. That is expected and harmless, but if it becomes noisy, drop the
`push: tags` trigger until the publisher exists.

**Token fallback:** `pip install build twine && python -m build && twine upload
dist/*`. Prefer Trusted Publishing — a token in CI is a long-lived secret that
will eventually leak, while OIDC credentials expire in minutes.

## 4. Launch, in this order

Post where the audience already is, not where you wish they were. Same day,
spread a couple of hours apart so you can answer questions in each.

| Where | Why | Notes |
|---|---|---|
| **r/FPGA** | The densest concentration of your exact user | Best-performing channel for this project. Lead with the screenshot, put the pain in the title. |
| **r/chipdesign** | Smaller, more senior; better for design feedback | Cross-post a day later with a different angle, not the same text. |
| **Hacker News** (`Show HN`) | Non-EDA people like a good dev-tool story | Title format: `Show HN: Wavediff – find the first moment two waveforms disagree`. Post ~14:00–16:00 UTC on a weekday. |
| **知乎 / 微信公众号（IC 方向）** | The Chinese EDA/IC community is large and underserved by English tools | The `README.zh-CN.md` already exists for this; write the post in Chinese, link the repo. |
| **HelloGitHub** | Curated, long-tail discovery | Submissions need a stable README and a licence — both done. |
| **Awesome-EDA / Awesome-Hardware lists** | Passive discovery for years | One PR each. Check the contribution rules first; a sloppy PR gets ignored. |

**What to say.** Not "I made a waveform diff tool". Lead with the pain, then the
single concrete number:

> Diagnosing a regression means scrolling two synchronized GTKWave windows
> looking for the one step that moved. wavediff tells you `t=30,
> tb.dut.count, 00000011 vs 00000111` — and exits non-zero so CI catches it.

**Answer every comment for the first 6 hours.** Launch-day ranking on HN and
Reddit is driven by early engagement velocity far more than by the content.

## 5. The first week

- Reply to every issue with a commit or a clear "not in scope, here is why". Early contributors decide whether the project has a future.
- Tag `good first issue` on the FST reader and the GitHub Action wrapper from the roadmap — they are well-scoped and genuinely useful.
- Ship `v0.1.1` within the first week fixing whatever the launch surfaced. A fast follow-up release is the strongest possible signal that the project is alive.
- Keep the README's first screen stable. Star conversion comes mostly from people who arrived from a link and never scroll.

## 6. What usually goes wrong

- **No screenshot.** The most common failure by a wide margin. Fix it before launching.
- **A stale ownership placeholder.** An unsubstituted `OWNER` makes a real project look like a template that nobody finished.
- **Launching with a broken CI badge.** Check the badge renders after your first push; run the workflow once and fix it *before* announcing.
- **Only posting to r/FPGA.** Good channel, but you leave HN and the Chinese community on the table.
- **Over-claiming.** The README is explicit that FST and the native parser are not done. That honesty is a feature: an engineer who finds a false claim leaves and never returns.
