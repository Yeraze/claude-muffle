# Changelog

## 0.3.0

Rules mined from Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing).
186 rules to 331; coverage of the phrases on that page went from 29/280 to
103/280.

**Fixed: verb swaps produced ungrammatical output.** Every third-person verb
mapped onto a bare stem, so "This demonstrates the bug" became "This show the
bug". Present since 0.1.0 and affecting `demonstrate`, `facilitate`, `utilize`,
`leverage`, `ensure`, `obtain`, `acquire`, `permit`, `assist`, `initiate`,
`commence`, `terminate`, `necessitate`, and `elevate`. The new `V()` helper
takes base / third-person / past / gerund on both sides and emits one rule per
form.

Also fixed: `highlight` was rewriting the imperative, turning "Highlight the
selected row" into "Shows the selected row". Bare `highlight` and `underscore`
are now left alone; only the inflected forms are swapped.

New categories, all on by default:

- `puffery` — significance inflation (WP:AILEGACY): "marking a pivotal
  moment", "nestled in", "faces challenges", "widely regarded as"
- `copula` — LLMs avoid plain "is" and "has": boasts → has, serves as → is,
  is home to → has, represents a → is a
- `chatbot` — assistant-speak in the prose: knowledge-cutoff disclaimers,
  "Would you like me to…", and flag-only placeholder detection

Added to existing categories:

- `punctuation` — curly quotes and apostrophes to straight, `…` to `...`, and
  removal of a horizontal rule sitting directly above a heading
- `hype` and `wordy` — the documented post-2022 vocabulary spikes: vibrant,
  enduring, renowned, bolster, garner, interplay, enhance, foster, emphasize,
  showcase, align with
- `filler` — "Additionally,", "Furthermore,", "Moreover,"
- `structure` — trailing "-ing" analyses, rule of three, title-case headings,
  "not a X but a Y", "no X, no Y, just Z"

Self-test now 38 cases.

## 0.2.0

- Em-dashes now get rewritten instead of only reported. The rule moved out of
  the flag-only `structure` category into a new `punctuation` category, which
  is on by default for both terminal text and files.
- An em-dash becomes a comma, drops to a space after existing punctuation, and
  disappears when it dangles at the end of a line. Numeric ranges, line-initial
  dashes, and en-dashes are left alone.
- Rule replacements can now be functions, for rules that need to look at what
  surrounds the match. `--list` labels them from `CALLABLE_LABELS`.
- Self-test covers the em-dash cases: 23 total.

## 0.1.0

First release.

- `MessageDisplay` hook rewrites assistant text as it streams to the terminal
- `PreToolUse` hook rewrites markdown before `Write` and `Edit` put it on disk
- 186 rules across nine categories in `scripts/llmisms.py`
- Standalone CLI: `--check`, `--list`, `--in-place`, `--on`, `--off`, `--selftest`
- Code masking for fenced blocks, inline backticks, indented blocks, HTML
  tags, URLs, markdown link targets, and YAML frontmatter
- Per-session fence tracking, so chunks inside a ``` block render untouched
- Config via `.claude-muffle.json` at project or home scope
- Secret redaction for `sk-ant-`, `ghp_`, and `AKIA` tokens
- `/muffle:check` and `/muffle:rules` commands
