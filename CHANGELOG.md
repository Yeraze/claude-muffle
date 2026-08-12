# Changelog

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
