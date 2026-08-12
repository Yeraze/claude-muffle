# Changelog

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
