# scratchpad.md: questions from Claude to Anbu (GitHub-only file; not in the GitLab project)

How this works: Claude writes a question here only when it cannot decide something that is yours to decide. Edit this file on GitHub, write your answer after `ANSWER:`, and commit. Claude re-reads it at every wake-up and never waits on it: it keeps building on the stated DEFAULT. Never paste tokens or passwords here (this repository is public).

## Status (updated Oct 13, 07:05 IST)
- Done today: audited by Opus (1 blocker, 10 fixes, all applied); reaction flow v1.5.0 published and live-tested; eight pre-registered Developer Flow runs on our repository (all eight stayed inside the issue; nothing for the card to flag); sample F audited (4 of 8 flagged merge requests held a real extra).
- Live proof for the video: with Draft lifted and auto-merge armed (what the organisers' demo loop does), an open Itemator thread keeps the merge blocked, and typing the name lets GitLab merge by itself within seconds.
- Next: README/Devpost refresh; maybe a rules v7 (new-dependency rule is the weak one: 0 of 5 real events on samples D and F); next Opus audit after 08:50.
- Credits today: about 25 to 30 used by estimate (cap 75; the meter lags about 18 h). GitHub commits today: 3 of 10 before this update.

## Open questions

### Q1. Should the Itemator triggers stay ON after the submission deadline? (decide by Oct 25)
Facts: the project's members include GitLab staff (Developer role), so a judge could open a merge request in our project and watch Itemator work live. The flows only react to a person's action (assign reviewer, mention, a person's merge request pipeline); they are not scheduled and not self-running. The Rules say nothing may change after the deadline and no "self-running flows".
DEFAULT: leave them ON, add a "Try it" section to the README, and (you, in the Oct 20 office hours at 10:00 UTC, or on the Devpost discussion forum) ask the organisers: "May event-triggered flows stay enabled after the deadline?" If they say no, I switch the triggers off on Oct 26.
ANSWER: Sure, will answer within October 25

### Q2. Office hours: please ask the organisers two things (Thu Oct 15 19:00 UTC or Tue Oct 20 10:00 UTC, or on Discord)
(a) The question in Q1. (b) "Duo Code Review is assigned automatically when a merge request is created. Does that interact with a custom flow that also triggers on reviewer assignment?" (we saw both fire).
ANSWER: Will ask and let you know

## Answered
- Q (Oct 12-13): Build Session transcript: answered by the user's paste (stored in the vault).
