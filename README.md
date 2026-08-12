# claude-muffle

A Claude Code plugin that strips LLM tics out of Claude's prose — in the
terminal as it streams, and in the markdown it writes to disk.

It never touches your code.

> Great question! It's important to note that in today's fast-paced world,
> developers utilize a comprehensive suite of tools. This robust framework
> empowers you to seamlessly delve into the realm of distributed systems.

becomes

> Developers use a full suite of tools. This solid framework lets you smoothly
> dig into distributed systems.

## Install

```
/plugin marketplace add Yeraze/claude-muffle
/plugin install muffle@claude-muffle
```

Restart Claude Code, or run `/reload-plugins`. Check it took with `/hooks` —
you should see `MessageDisplay` and two `PreToolUse` entries.

Needs Python 3.8+ on your PATH as `python3`. No packages, no network.

## What it does

Two hooks, doing two different jobs.

| | terminal text | markdown files |
| --- | --- | --- |
| hook | `MessageDisplay` | `PreToolUse` on `Write`/`Edit` |
| scope | assistant message text only | files matching `**/*.md` |
| effect | what you see | what lands on disk |
| reversible | yes, the transcript keeps the original | no |
| Claude sees it | no | yes, on the next read |

`MessageDisplay` is a view filter. It cannot block a message or change the
transcript, and `--verbose` shows you the untouched text. Your commands, tool
output, and anything you type render normally.

`PreToolUse` returns `updatedInput`, which really does rewrite the file. That
path runs a smaller, safer rule set, and asks before applying — see below.

## The rules

186 rules in ten categories.

| category | catches | terminal | files |
| --- | --- | :---: | :---: |
| `sycophancy` | "Great question!", "You're absolutely right" | on | on |
| `filler` | "It's important to note that", "in order to" | on | on |
| `closer` | "I hope this helps!", "Feel free to…" | on | on |
| `cliche` | "delve into", "a testament to", "unlock the power of" | on | on |
| `punctuation` | em-dashes → commas | on | on |
| `corporate` | "circle back", "reach out", "synergy" | on | off |
| `hype` | "very", "robust", "seamless", "cutting-edge" | on | off |
| `wordy` | utilize → use, leverage → use, ensure → make sure | on | off |
| `structure` | "not just X, but Y", bold-lead bullets, "let's" | flag only | flag only |
| `emoji` | decorative emoji | off | off |

### Em-dashes

`punctuation` runs on both paths, including files, because the swap is
mechanical rather than a judgment call. An em-dash becomes a comma:

| before | after |
| --- | --- |
| `The plan — such as it is — ships Friday.` | `The plan, such as it is, ships Friday.` |
| `It is fast—cheap too.` | `It is fast, cheap too.` |
| `Wait, — that is wrong.` | `Wait, that is wrong.` |
| `Trailing thought —` | `Trailing thought` |

Four cases are left alone: numeric ranges (`2019—2024`), line-initial dashes
(`— Anonymous`, list markers), and anything inside code or a URL. En-dashes
are never touched.

Turn it off by dropping `"punctuation"` from `display`, `file`, or both in
`.claude-muffle.json`.

Files get the conservative set on purpose. Those four categories remove
throat-clearing that nobody misses; the word-level swaps have more false
positives, and a bad rewrite on disk is permanent.

**Flag-only rules never rewrite anything.** Turning "not just X, but Y" into a
real sentence takes judgment, so `structure` only reports under `--check`.

### Your code is safe

Before any rule runs, these are masked out and restored afterward:

- fenced code blocks and inline backticks
- indented code blocks (but not indented list items)
- HTML and JSX tags
- URLs and markdown link targets
- YAML frontmatter

So `config.leverage = True` and a `utilize_cache` flag survive untouched.

The terminal path needs extra care: messages stream in chunks, one hook run
each, so a chunk landing inside a ``` block carries no fence marker and would
read as ordinary prose. The plugin tracks fence state per session in
`$TMPDIR/claude-muffle` and passes those chunks through unchanged.

## Configure

Everything is optional. Drop a `.claude-muffle.json` in your project root, or
in `$HOME` to apply it everywhere:

```json
{
  "display":  ["sycophancy", "filler", "closer", "cliche", "punctuation",
               "corporate", "hype", "wordy"],
  "file":     ["sycophancy", "filler", "closer", "cliche", "punctuation"],
  "decision": "ask",
  "redact":   true
}
```

| key | meaning |
| --- | --- |
| `display` | categories applied to terminal text |
| `file` | categories applied to markdown on disk |
| `decision` | `"ask"` shows each file rewrite in a permission prompt; `"allow"` applies it silently |
| `redact` | mask API keys and tokens (`sk-ant-`, `ghp_`, `AKIA…`) on both paths |

Leave a key out and it keeps its default. Set `"file": []` to leave your files
alone entirely, or `"display": []` to keep the terminal untouched.

Lookup order — first hit wins:

1. `$CLAUDE_MUFFLE_CONFIG`
2. `$CLAUDE_PROJECT_DIR/.claude-muffle.json`
3. `~/.claude-muffle.json`

`decision` starts at `"ask"` so you can see every file rewrite before it lands.
Once the rules behave, switch to `"allow"` and the prompts stop.

**Do not edit files inside the plugin directory.** Claude Code replaces it on
every update and your changes will vanish. That is what the config file is for.

## Commands

| command | does |
| --- | --- |
| `/muffle:check [path]` | report the LLM-isms in a file, change nothing |
| `/muffle:rules [filter]` | show the rule database and which categories are live |

## Standalone CLI

`llmisms.py` is a plain script with no dependencies. Useful on its own for
docs, commit messages, or anything else:

```bash
llmisms.py --list           # the whole rule database
llmisms.py --check doc.md   # what would fire, and where
llmisms.py -i doc.md        # rewrite in place
llmisms.py --on all doc.md  # every category, including emoji
llmisms.py --off wordy doc.md
cat doc.md | llmisms.py     # or pipe it
llmisms.py --selftest       # 16 cases
```

`--check` prints `path:line  category  matched-text  fix` and exits non-zero
when it finds something, so it drops into CI or a pre-commit hook:

```bash
python3 scripts/llmisms.py --check docs/*.md || exit 1
```

After the plugin is installed, the script lives in the plugin cache. Find it
with:

```bash
find ~/.claude/plugins/cache -name llmisms.py
```

Or just clone this repo and run it from `scripts/`.

## Without the plugin system

If you would rather wire the hooks up by hand, clone the repo and add this to
`.claude/settings.json`, pointing at wherever you put it:

```json
{
  "hooks": {
    "MessageDisplay": [
      { "hooks": [{
          "type": "command", "command": "python3",
          "args": ["/path/to/claude-muffle/scripts/display_hook.py"],
          "timeout": 10 }] }
    ],
    "PreToolUse": [
      { "matcher": "Write", "hooks": [{
          "type": "command", "if": "Write(**/*.md)", "command": "python3",
          "args": ["/path/to/claude-muffle/scripts/write_hook.py"] }] },
      { "matcher": "Edit", "hooks": [{
          "type": "command", "if": "Edit(**/*.md)", "command": "python3",
          "args": ["/path/to/claude-muffle/scripts/write_hook.py"] }] }
    ]
  }
}
```

## Writing your own rules

Rules live in the `RULES` list in `scripts/llmisms.py`. Each one is a
category, a pattern, a replacement, and a label:

```python
R("cliche", r"\bdelv(?:e|es|ing) into\b", "dig into", "delve into"),
R("filler", r"\bit(?:'s| is) worth noting that\s+", CUT, "It's worth noting that"),
R("structure", r"\bnot just\b[^.!?\n]{0,80}?\bbut\b", FLAG, "not just X, but Y"),
```

A replacement is a string, one of three markers, or a function:

- a plain string — swap it in, inheriting the case of what it replaced
- `X` — delete it, for mid-sentence words like "very"
- `CUT` — delete it and capitalize what follows, for sentence openers
- `FLAG` — report only, never rewrite
- a function taking the match and returning the replacement, for rules that
  need to see what surrounds the match. `em_dash` is the one that does this;
  add a label for it in `CALLABLE_LABELS` so `--list` can describe it.

Everything is matched case-insensitively, and replacements inherit the case of
what they replace, so "Utilize" becomes "Use". Order matters: long phrases go
before the words inside them, so `delve into` wins before `delve` sees the
text.

After a deletion the text gets tidied — sentence-initial cuts recapitalize the
next word, doubled spaces collapse, and `a`/`an` is repaired when a swap
changes the following sound ("an abundance of" → "plenty of").

Add a case to `CASES` and run `--selftest`.

## Failure behavior

Both hooks fail open. An exception, a timeout, or malformed input produces no
output, and Claude Code uses the original text. Both also stay silent when the
transform changes nothing, so a rule that does not fire costs no prompt and no
latency.

## Caveats

The rules are opinionated and will over-fire on some prose. Run `--check` on a
real document before turning `wordy` loose on files.

`--check` reports every matching rule independently, so overlapping ones
("reach out to" and "reach out") both appear even though only the longer one
wins in a rewrite.

Terminal text arrives in chunks, so a rule needing a whole paragraph may only
see part of one. Line-level rules are safe.

## License

GPL-3.0
