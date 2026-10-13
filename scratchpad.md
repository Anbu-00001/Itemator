# scratchpad.md: questions from Claude to Anbu (GitHub-only file; not in the GitLab project)

How this works: Claude writes a question here only when it cannot decide something that is yours to decide. Edit this file on GitHub, write your answer after `ANSWER:`, and commit. Claude re-reads it at every wake-up and never waits on it: it keeps building on the stated DEFAULT. Never paste tokens or passwords here (this repository is public).

## Status (updated Oct 13, morning)
- Done today: the policy-edit gap fixed and committed; Build Session transcript stored and analysed (clarity first; the judges' own demo loop ends in an automatic merge, and our "All threads must be resolved" lock is the brake); storyboard v3 written (five shots).
- Running: the first Opus audit pass (reaction-flow prompt, `always`, the gap fix). Next: live test that an armed auto-merge waits for an open Itemator thread and then merges by itself once the name is typed (about 3 credits).
- Credits today: meter 97.6 at 05:41; stop at 172.6. GitHub commits today: 3 of 10.

## Open questions

### Q1. Should the Itemator triggers stay ON after the submission deadline? (decide by Oct 25)
Facts: the project's members include GitLab staff (Developer role), so a judge could open a merge request in our project and watch Itemator work live. The flows only react to a person's action (assign reviewer, mention, a person's merge request pipeline); they are not scheduled and not self-running. The Rules say nothing may change after the deadline and no "self-running flows".
DEFAULT: leave them ON, add a "Try it" section to the README, and (you, in the Oct 20 office hours at 10:00 UTC, or on the Devpost discussion forum) ask the organisers: "May event-triggered flows stay enabled after the deadline?" If they say no, I switch the triggers off on Oct 26.
ANSWER:

### Q2. Office hours: please ask the organisers two things (Thu Oct 15 19:00 UTC or Tue Oct 20 10:00 UTC, or on Discord)
(a) The question in Q1. (b) "Duo Code Review is assigned automatically when a merge request is created. Does that interact with a custom flow that also triggers on reviewer assignment?" (we saw both fire).
ANSWER:

## Answered
- Q (Oct 12-13): Build Session transcript: answered by the user's paste (stored in the vault).
