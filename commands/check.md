---
description: Report the LLM-isms in a file without changing it. Pass a path, or omit for the files changed in this session.
---

Run the claude-muffle checker over the file(s) the user named in `$ARGUMENTS`.
If they named none, check the markdown files changed in this session; if there
are none of those either, ask which file they mean.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/llmisms.py" --check <paths>
```

Each line comes back as `path:line  category  matched-text  fix`. A fix of
`(needs a human)` marks a flag-only rule -- those are structural tics like
"not just X, but Y" that no regex can rewrite safely.

Summarize what you find: group by category, lead with whatever appears most,
and quote two or three of the worst lines. Do not rewrite the file unless the
user asks. If you do rewrite it, prefer fixing the flagged structures by hand
over running `--in-place`, since the automatic pass only handles the
mechanical substitutions.

Note that overlapping rules both report, so "reach out to" and "reach out" can
appear on the same line. Only the longer one fires in an actual rewrite.
