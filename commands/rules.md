---
description: Show the claude-muffle rule database, or explain which rules are active right now.
---

Print the rule database:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/llmisms.py" --list
```

Then show the user which categories are actually running. Read their config
from the first of these that exists, and fall back to the defaults in
`${CLAUDE_PLUGIN_ROOT}/scripts/muffle.py` if none do:

- `$CLAUDE_MUFFLE_CONFIG`
- `$CLAUDE_PROJECT_DIR/.claude-muffle.json`
- `~/.claude-muffle.json`

Report it as two short lists -- what runs on terminal text, and what runs on
markdown files -- and note that the two differ on purpose: files get the
conservative set because those rewrites are permanent.

If `$ARGUMENTS` names a category or a phrase, narrow the output to the
matching rules instead of dumping all of them.
