# L: labeller (one Haiku and one Sonnet per shard range; each alone). Report: reports/L-<TIER>-<RANGE>.md (the launch message gives TIER, RANGE and the shard files)
Read 00-common.md in this folder first. Read only the shard files your launch message names (in /home/anbu/26_class/LifeAfterCode/vault/Intel/fleet-33-2026-10-18/shards/). No web access is needed; do not browse.

Each note in a shard was written by a person (not the merge request's author, not a bot) on a merge request that GitLab Duo's Developer Flow (an AI agent) opened. For EVERY note in your shards, answer one question:

**Does this note say that a specific part of this change was not asked for, does not belong in this merge request, or should be removed, split into another merge request, or reverted?**

- `yes`: the note says that about some part of the change (a file, a line, a dependency, a config or CI change, a test, a doc edit, generated or unrelated code). Questions count when they clearly object ("why is this file changed? it is not part of the issue"). 
- `no`: anything else: style or naming comments, bugs in the asked-for code, requests to add something, approvals, thanks, questions about how something works, pipeline chatter, rebase requests, a reviewer asking the agent to do the asked work differently.
- `unclear`: you cannot tell from the note alone.

Do not guess from the file list; judge only what the note says. Do not look up anything else.

## Output (the report file)
First line `STATUS: done` (or `partial` with the last note number you reached). Then exactly one line per note, in order, in this form, nothing else on the line:

`NOTE <number> | <yes|no|unclear> | <file path the note points at, or -> | "<quote of at most 40 words from the note that shows it, or - for no>"`

For a `yes`, the file is the one the note is about: the diff note's own file if it says "on the line of file", else a path the note names; `-` if it names none. Copy paths and quotes character for character from the shard. After the last NOTE line, one line `COUNTS yes=<n> no=<n> unclear=<n>` and a last line `NEXT:` one sentence.
