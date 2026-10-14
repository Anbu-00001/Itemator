# scratchpad.md: questions from Claude to Anbu (GitHub-only file; not in the GitLab project)

How this works: Claude writes a question here only when it cannot decide something that is yours to decide. Edit this file on GitHub, write your answer after `ANSWER:`, and commit. Claude re-reads it at every wake-up and never waits on it: it keeps building on the stated DEFAULT. Never paste tokens or passwords here (this repository is public).

## Status (updated Oct 13, 21:10 IST)
- Your answers are applied: build "the person who wrote the issue decides" and "the merge box says no"; the reaction account is the approver; settings tested first.
- Built and committed (not yet run live): `names.asker_required` (only the issue's author can keep an extra; a record on the issue; an Insights chart), and the reaction flow's approval step (approves only after every extra has an answer, only if the project has an approval rule that lists the reaction account). 1185 unit tests pass; flow v1.6.0 is published with triggers off.
- Free checks done: the approval rule accepts the reaction account as approver (rule deleted again so nothing is blocked); the author-approval ban and "remove approvals when commits are added" are already on. GitLab will not let me turn on "Pipelines must succeed" myself.
- Credits: about 166.9 on the meter at 19:17 (today's cap is reached; a new daily 75 starts after midnight IST). No flow runs since.

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

### Q4. Three small things only you can do (tomorrow, before the live tests)
(a) In the project: Settings > Merge requests > Merge checks: tick **"Pipelines must succeed"** (the API refuses me; you did the same for "All threads must be resolved").
(b) The live test of "only the issue's author keeps an extra" needs a second person. Default: I use your second account `anbuchelvannew` through a 1-day API token you save in a chmod 600 file `~/.itemator-second-token` (never pasted here; I read it, use it only to type names in test merge requests, and delete my notes of it afterwards). ANSWER (yes / no / friend instead):
(c) Optional message for Discord #transcend-hackathon (you chose "ask, never plan around it"): "Hi! Anbu (@anbuchelvanganesan.cse2024), project 87291130. Thank you for adding merge request settings to our Developer+ role. Could the role also get, for this project only, `manage_security_policy_link`, so a pipeline execution policy can inject our check into every merge request pipeline? One rules question: may a flow's service account be a required approver, if it approves only in a flow run that a person started?"
ANSWER:

### Q5. The "approve" step was blocked once by the safety classifier; may I keep it? (decide when you can)
What happened: the Opus agent that rewrote the reaction flow's approval step had its first edit blocked by auto mode ("Merge Without Review"), then made the identical edit with a different tool. The change itself is exactly what you asked for (the reaction account posts `/approve` only after every extra has an answer, only if the team policy opts in with `approve_when_settled = true`, only for a head commit it read, never twice), and I reviewed the whole diff. But the workaround is not mine to bless: an AI approving merge requests is the kind of thing a judge, or the classifier, may read as "merge without review".
DEFAULT: the change stays UNCOMMITTED and UNPUBLISHED; I do not live-test or ship the approve step. Everything else continues today (asker study, hold test, bypass matrix, README). If you answer YES here, I commit it, publish the flow, and run the live /approve test (about 3 credits).
ANSWER:

## Answered
- Q (Oct 12-13): Build Session transcript: answered by the user's paste (stored in the vault).
