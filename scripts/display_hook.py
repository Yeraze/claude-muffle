#!/usr/bin/env python3
"""MessageDisplay adapter: rewrites assistant text on its way to the terminal.

Display-only. The transcript keeps the original, Claude never sees the
replacement, and `--verbose` shows the original. Nothing here can corrupt
the conversation.

Input on stdin has the pending chunk in `delta`. Output goes on stdout as
`hookSpecificOutput.displayContent`. Claude Code holds the chunk until this
exits, so keep it fast; the timeout for this event defaults to 10s and a
failure falls back to the original text.

FENCED CODE. Messages arrive in chunks, one hook run each, so a chunk landing
in the middle of a ``` block carries no fence marker and would look like
ordinary prose -- the transform would happily rewrite your code on screen.
So we track fence state per session in a temp file: a chunk that opens,
closes, or sits inside a fence is passed through untouched. State lives in
$TMPDIR/claude-muffle and is keyed by session_id.

Test by hand:
    echo '{"session_id":"t","delta":"Great question! We utilize it."}' \
      | python3 display_hook.py
"""

import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from muffle import muffle  # noqa: E402

STATE_DIR = os.path.join(tempfile.gettempdir(), "claude-muffle")


def fence_flag(session_id):
    """Path whose existence means 'this session is inside a code fence'."""
    name = re.sub(r"[^A-Za-z0-9_-]", "", str(session_id or "default"))[:64] or "default"
    return os.path.join(STATE_DIR, name + ".fence")


def main():
    data = json.load(sys.stdin)
    delta = data.get("delta")
    if not isinstance(delta, str) or not delta:
        return

    flag = fence_flag(data.get("session_id"))
    inside = os.path.exists(flag)

    fences = delta.count("```")
    if fences % 2:  # this chunk flips us in or out of a fence
        os.makedirs(STATE_DIR, exist_ok=True)
        if inside:
            os.remove(flag)
        else:
            open(flag, "w").close()

    if inside or fences:
        return  # code, or a fence boundary: render it exactly as written

    out = muffle(delta, {"source": "display", "path": None})
    if out == delta:
        return  # unchanged: stay silent, Claude Code renders the original

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "MessageDisplay",
                "displayContent": out,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail open: no output means the original text renders
