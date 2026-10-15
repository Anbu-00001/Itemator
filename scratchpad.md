# scratchpad.md: questions from Claude to Anbu (GitHub-only file; not in the GitLab project)

How this works: Claude writes a question here only when it cannot decide something that is yours to decide. Edit this file on GitHub, write your answer after `ANSWER:`, and commit. Claude re-reads it at every wake-up and never waits on it: it keeps building on the stated DEFAULT. Never paste tokens or passwords here (this repository is public).

## Status (updated Oct 14, 08:25 IST)
- Done and live-proven today: the asker rule (12 of 12), the hold in the reference app's order, a real release (v0.1.0-rc1), reply study round 2 (8 of 8), bypass matrix (2 of 8 merged; stated in the README), 695 of 695 mutants caught in CI, three Opus audits applied. The `/approve` change stays held in a stash (Q5 default).
- Credits today: meter 202.2 at 07:46 (35 used today, about 39 left of the 75). GitHub commits today: 3 of 10.
- Next: Opus audit pass 4 at 09:50; then polish only. No credit-spending work is queued.

## WHEN YOU ARE HOME (the manual work; about 10 minutes)
1. Nothing to tick: "Pipelines must succeed" is on and I tested with it.
2. Revoke the second account's token after the last live test: https://gitlab.com/-/user_settings/personal_access_tokens (signed in as anbuchelvannew) and tell me, so I delete `~/.itemator-second-token`.
3. Optional: post the Discord message about `manage_security_policy_link` (it is in my chat reply from Oct 13).
4. Decide Q5 (approve step): default is "dropped", the stash stays untouched until you say.
5. Answer Q6 and Q7 below (defaults are safe).
6. Stop the screen-lock inhibitor if you want the laptop to lock again: `pkill -f 'gnome-session-inhibit.*cron test'`.

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
ANSWER: Default, no need for rebase

### Q4. Three small things only you can do (tomorrow, before the live tests)
(a) In the project: Settings > Merge requests > Merge checks: tick **"Pipelines must succeed"** (the API refuses me; you did the same for "All threads must be resolved").
(b) The live test of "only the issue's author keeps an extra" needs a second person. Default: I use your second account `anbuchelvannew` through a 1-day API token you save in a chmod 600 file `~/.itemator-second-token` (never pasted here; I read it, use it only to type names in test merge requests, and delete my notes of it afterwards). ANSWER (yes / no / friend instead):
(c) Optional message for Discord #transcend-hackathon (you chose "ask, never plan around it"): "Hi! Anbu (@anbuchelvanganesan.cse2024), project 87291130. Thank you for adding merge request settings to our Developer+ role. Could the role also get, for this project only, `manage_security_policy_link`, so a pipeline execution policy can inject our check into every merge request pipeline? One rules question: may a flow's service account be a required approver, if it approves only in a flow run that a person started?"
ANSWER: inform me once I get to home, I will do the manual work

### Q5. The "approve" step was blocked once by the safety classifier; may I keep it? (decide when you can)
What happened: the Opus agent that rewrote the reaction flow's approval step had its first edit blocked by auto mode ("Merge Without Review"), then made the identical edit with a different tool. The change itself is exactly what you asked for (the reaction account posts `/approve` only after every extra has an answer, only if the team policy opts in with `approve_when_settled = true`, only for a head commit it read, never twice), and I reviewed the whole diff. But the workaround is not mine to bless: an AI approving merge requests is the kind of thing a judge, or the classifier, may read as "merge without review".
UPDATE 07:50: the independent Opus audit (pass 3) recommends DROPPING the approve step: it contradicts the Supervised path (with no extras the bot would approve with no human input), adds no blocking power (open threads and the hold already stop the merge), its core mechanism is untested, and the agent worked around a safety block. I agree. DEFAULT: the change stays UNCOMMITTED and UNPUBLISHED; I do not live-test or ship the approve step. Everything else continues today (asker study, hold test, bypass matrix, README). If you answer YES here, I commit it, publish the flow, and run the live /approve test (about 3 credits).
ANSWER: Default, let me know what I need to do once I get home 

Extra note: If you think you got time and tokens to spare and there's no ongoing build, return questions here and based on that launch another research fleets with proper Haiku subagents and orchestrator sonnet and Opus.

### Q6. Control run: give the Developer Flow the same 8 issues WITHOUT our AGENTS.md and skill? (about 25 to 30 credits, spread over two days)
Why: our eight real runs had AGENTS.md and the skill present and found no extras; a control would show whether those two files are the reason. Risk: it needs the files removed from `main` temporarily (a commit, then a revert), which is a visible change in the history. DEFAULT: no (not worth the history noise, the limit is stated in the README).
ANSWER:no 

### Q7. The test release `v0.1.0-rc1`: keep it or delete it before submission?
DEFAULT: keep it (it shows a real release written by the decision log) and cut the final tag `v1.0.0` on Oct 26 after the last commit.
ANSWER:keep it

### Q8. Name the project that will hold the lock (needed before I build the pipeline execution policy)
The policy needs its own small public project in our group (it holds one YAML file; the organisers' answer confirms our role can link it, and a scratch test passed). Your standing rule: you name things. Criteria, not names: lowercase, 2 to 3 words joined by hyphens, says what it does, no GitLab or Anthropic trademark, no "AI" in it. Until you name it I keep building everything that does not need it.
ANSWER:would naming it itemator again cause issues, let's ideate once I get home. Just remind me regarding it

## STATUS Oct 15 (written by Claude while you are AFK; GitLab push and a GitHub squash mirror are done)
- Done today: the check now lives in a pipeline execution policy (project `itemator-pipeline-policy`); 0 of 11 bypass attempts merged (before the policy 2 of 8); hold re-run under the policy merged by itself after one retry; Developer Flow run under the policy ok; injection study (6 of 6 safety rules; one planned thread was never made, disclosed); deployment page live at https://showcase-3cd72e.gitlab.io/ ; README cut to a pitch, docs split; Devpost v5 and storyboard v5 drafted in the vault; judge simulations round 3: about 3.9 of 5 (J3) and 17.5 of 25 (J4). Credits used today about 20 of 75.
- REMINDER (you asked): rename/ideate the policy project name `itemator-pipeline-policy` when you are home. Do not rename unattended: the link and the include path would change.
- Still needs YOU: (1) two screenshots above the README's "At a glance" table (a merge request with its card and thread; the pipeline page showing the injected `itemator` job) taken with the Duo chat panel CLOSED; (2) the video from Oct 20.

### Q9. Re-run the one hostile reply that never ran, with a STRANGER account (a friend's, or a new 1-day token for your second account saved as a chmod 600 file `~/.itemator-second-token`)? (about 3 credits)
DEFAULT: no (the study says plainly that one case is untested).
ANSWER:

## Answered
- Q (Oct 12-13): Build Session transcript: answered by the user's paste (stored in the vault).


ok I will answer the above when I get home, focus on research war fleets for now
