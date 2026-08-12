#!/usr/bin/env python3
"""PreToolUse adapter: rewrites markdown before Write or Edit puts it on disk.

Unlike the display hook, this changes real content. It returns the whole
tool input back under `updatedInput` -- that field replaces the entire input
object, so every unchanged field has to be echoed along with the rewritten
one.

Which fields get rewritten:
    Write  content
    Edit   new_string only. `old_string` has to match the file byte for byte,
           so rewriting it would break the edit.

The `decision` setting in .claude-muffle.json controls what happens next.
"ask" shows you the rewritten input in the permission prompt -- the right
setting while you are tuning rules. Switch to "allow" once you trust them
and want the prompt to go away. See muffle.py for where config lives.

Test by hand:
    echo '{"tool_name":"Write","tool_input":{"file_path":"/tmp/a.md","content":"key sk-ant-'"$(printf 'x%.0s' {1..25})"'"}}' \
      | python3 write_hook.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from muffle import CONFIG, muffle  # noqa: E402

# "ask" shows each rewrite in a permission prompt, "allow" applies it
# silently. Set it in .claude-muffle.json, not here.
DECISION = CONFIG.get("decision", "ask")

FIELDS = {"Write": ("content",), "Edit": ("new_string",)}
MARKDOWN = (".md", ".markdown", ".mdx")


def main():
    data = json.load(sys.stdin)
    fields = FIELDS.get(data.get("tool_name"))
    if not fields:
        return

    tool_input = data.get("tool_input") or {}

    # The `if` clause in settings.json already scopes this to markdown. This
    # is the backstop, so a settings edit can never point it at source code.
    path = tool_input.get("file_path", "")
    if not path.lower().endswith(MARKDOWN):
        return

    updated = dict(tool_input)  # updatedInput replaces the whole object
    changed = []
    for field in fields:
        before = updated.get(field)
        if not isinstance(before, str) or not before:
            continue
        after = muffle(before, {"source": "file", "path": path})
        if after != before:
            updated[field] = after
            changed.append(field)

    if not changed:
        return  # unchanged: stay silent and let the normal flow proceed

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": DECISION,
                "permissionDecisionReason": "claude-muffle rewrote "
                + ", ".join(changed),
                "updatedInput": updated,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail open: no output means the tool call proceeds untouched
