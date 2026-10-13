# scratchpad.md: questions from Claude to Anbu (GitHub-only file; not in the GitLab project)

How this works: Claude writes a question here only when it cannot decide something that is yours to decide. Edit this file on GitHub, write your answer after `ANSWER:`, and commit. Claude re-reads it at every wake-up and never waits on it: it keeps building on the stated DEFAULT. Never paste tokens or passwords here (this repository is public).

## Status (updated Oct 13, 19:00 IST)
- The crons did not fire on Oct 13, so nothing ran from about 08:00 to 17:40; work resumed when you came back. Sorry.
- Done since: second Opus audit applied (one wrong README claim fixed, plus eleven smaller fixes); the fixes went through a real merge request that Itemator itself judged (two extras, both named, merged); a decision log that touches the Release and Monitor stages (all nine stages now); 625 mutants all caught in CI; unit tests now run in every pipeline; `always` re-tested live on the tightened prompt.
- Honest gap, now stated in the README: in the organisers' own auto-merge loop the merge is armed inside the pipeline, before the card exists, so GitLab can merge first.
- Credits today: about 160 on the meter plus a few not yet shown; I am not spending more today. GitHub commits today: 6 of 10 after this update.

## Open questions

### Q1. Should the Itemator triggers stay ON after the submission deadline? (decide by Oct 25)
Facts: the project's members include GitLab staff (Developer role), so a judge could open a merge request in our project and watch Itemator work live. The flows only react to a person's action (assign reviewer, mention, a person's merge request pipeline); they are not scheduled and not self-running. The Rules say nothing may change after the deadline and no "self-running flows".
DEFAULT: leave them ON, add a "Try it" section to the README, and (you, in the Oct 20 office hours at 10:00 UTC, or on the Devpost discussion forum) ask the organisers: "May event-triggered flows stay enabled after the deadline?" If they say no, I switch the triggers off on Oct 26.
ANSWER: Sure, will answer within October 25

### Q2. Office hours: please ask the organisers two things (Thu Oct 15 19:00 UTC or Tue Oct 20 10:00 UTC, or on Discord)
(a) The question in Q1. (b) "Duo Code Review is assigned automatically when a merge request is created. Does that interact with a custom flow that also triggers on reviewer assignment?" (we saw both fire).
ANSWER: Will ask and let you know

### Q3. A commit by GitLab's Developer Flow carries your institutional email in a public project (your call)
Facts: the flow signs its commits "Signed-off-by: <your name> <your institutional email>" on the closed merge requests !26 to !33 (the field study). They are visible in a public project; I cannot remove them. I have added a line to AGENTS.md telling agents never to sign off in a person's name, and the sign-off check now exempts only our own flow accounts.
DEFAULT: leave the closed merge requests as they are. If you want them hidden, only a project owner can delete a merge request.
ANSWER:

## Answered
- Q (Oct 12-13): Build Session transcript: answered by the user's paste (stored in the vault).
