"""Core text transform for claude-muffle.

Both hook adapters call `muffle()` and do nothing else of substance.

    muffle(text, ctx) -> str

    text  the text to rewrite
    ctx   {"source": "display" | "file", "path": str | None}
          "display" = a chunk of an assistant message on its way to the
                      terminal. Cosmetic only, never saved.
          "file"    = markdown about to be written to disk. Real content.
          "path"    = the target file, for "file" only.

CONFIGURATION. This file lives inside the plugin cache, which Claude Code
replaces on every update, so do not edit it -- your changes will vanish.
Settings come from a `.claude-muffle.json` file instead, and the first of
these that exists wins:

    $CLAUDE_MUFFLE_CONFIG
    $CLAUDE_PROJECT_DIR/.claude-muffle.json    (per project)
    ~/.claude-muffle.json                      (everywhere)

Every key is optional; anything you leave out keeps the default below.

    {
      "display":  ["sycophancy", "filler", "closer", "cliche",
                   "corporate", "hype", "wordy"],
      "file":     ["sycophancy", "filler", "closer", "cliche"],
      "decision": "ask",
      "redact":   true
    }

    display   rule categories applied to terminal text
    file      rule categories applied to markdown on disk
    decision  "ask" shows each file rewrite in a permission prompt,
              "allow" applies it silently
    redact    mask API keys and tokens on both paths

Set "display" or "file" to [] to turn that path off entirely. Run
`python3 llmisms.py --list` to see every category and rule.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llmisms import CATEGORIES, scrub  # noqa: E402

DEFAULTS = {
    # Terminal text is throwaway, so it gets the full treatment.
    "display": ["sycophancy", "filler", "closer", "cliche", "puffery", "copula",
                "chatbot", "punctuation", "contractions", "corporate", "hype", "wordy"],
    # Files are real, so they get the rules with the fewest false positives.
    # Word swaps like "ensure" -> "make sure" and the meeting-room verbs stay
    # off on disk until you opt in.
    "file": ["sycophancy", "filler", "closer", "cliche", "puffery", "copula",
             "chatbot", "punctuation", "contractions"],
    "decision": "ask",
    "redact": True,
}

CONFIG_NAME = ".claude-muffle.json"


def config_paths():
    override = os.environ.get("CLAUDE_MUFFLE_CONFIG")
    if override:
        yield override
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        yield os.path.join(project, CONFIG_NAME)
    yield os.path.join(os.getcwd(), CONFIG_NAME)
    yield os.path.join(os.path.expanduser("~"), CONFIG_NAME)


def load_config():
    settings = dict(DEFAULTS)
    for path in config_paths():
        try:
            with open(path, encoding="utf-8") as handle:
                found = json.load(handle)
        except (OSError, ValueError):
            continue  # missing or malformed: fall through to the next
        if isinstance(found, dict):
            settings.update(found)
        break
    return settings


CONFIG = load_config()

SECRETS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "sk-ant-<redacted>"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "gh_<redacted>"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA<redacted>"),
]


def categories(source):
    """Valid, enabled rule categories for one path. Unknown names are dropped."""
    wanted = CONFIG.get("display" if source == "display" else "file") or []
    return {c for c in wanted if c in CATEGORIES}


def muffle(text, ctx):
    if CONFIG.get("redact", True):
        for pattern, replacement in SECRETS:
            text = pattern.sub(replacement, text)

    enabled = categories(ctx["source"])
    if enabled:
        text = scrub(text, enabled)[0]

    return text
