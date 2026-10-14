# Use Itemator in your own project

We created the flows in this project through GitLab's GraphQL API; the menu path below (AI > Flows) is the documented one and is untested by us. We have not installed Itemator in a second project.

**You need:** GitLab with the Duo Agent Platform and custom flows turned on, a role that can create AI flows and triggers (ours was a custom Developer + AI role), and a Python 3.12 runner image for the CI job.

## 1. The CI job
1. Copy the `itemator/` folder to the root of your repository.
2. Copy the `itemator` job from this project's [.gitlab-ci.yml](../.gitlab-ci.yml) into yours. It runs only in merge request pipelines, so your `workflow:rules` must allow them (see the top of the same file).
3. Optional: copy [.itemator.toml](../.itemator.toml) and read its comments. The job reads that file, and runs the checker itself, from the branch the merge request targets, so a merge request cannot change the rules it is judged by.

## 2. The two flows
In the project, open **AI** > **Flows** > **New flow**, choose **Private**, and paste the contents of [flows/itemator_card.yml](../flows/itemator_card.yml). Do the same for [flows/itemator_react.yml](../flows/itemator_react.yml). GitLab creates one service account per flow, named like `ai-itemator-card-<your group>` and `ai-itemator-react-<your group>`.

**Change two names in the reaction flow.** Its prompt names the two accounts exactly (`CARD_BOT` and `REACT_BOT`). Replace them with the account names GitLab created in your group; only notes from those two accounts then count as cards or settled answers.

## 3. The triggers
In **AI** > **Triggers** > **New flow trigger** (Maintainer role):
- Card flow: an event for a finished merge request pipeline (success and failed, source merge request) and **Assign reviewer**. Service account: the card account.
- Reaction flow: **Mention**, **Merge request** with the **Approved** action, and the merge request **ready** event. Service account: the reaction account.

A flow can only be started by a person's action: a bot cannot start a trigger, which is also why the flows cannot start each other.

## 4. Make the threads a lock (optional, needs the Maintainer role)
In **Settings** > **Merge requests**, turn on **All threads must be resolved**. Until then an unnamed extra puts the merge request in Draft but does not stop the merge button.

## 5. The team policy (optional): `.itemator.toml`
Put it at the root of the branch merge requests target; it is read from there, never from the merge request. Every key is optional and an unknown key makes the whole file ignored (the card says why).
```toml
[names]
other_person_required = false   # true: only someone other than the author can name an extra
hold_until_named = false        # true: the itemator job fails while an extra has no name (see below)
asker_required = false          # true: only the person who wrote the linked issue can keep an extra

[ignore]
kinds = []   # whole kinds of extras to quiet, e.g. ["whitespace_only"]; never policy_changed, binary_or_large_added or agent_instructions
paths = []   # file paths or shell-style patterns to quiet (`*` also crosses `/`); at most twenty entries; a package manifest only if its dependencies are known to the registries
```
The `always` answer edits this file for you, one line at a time, in a merge request your team reviews. It is offered only when the `[ignore]` table has exactly one line that starts with `paths = [` and ends the list on the same line (no `#` inside the list, no trailing comma); with `paths=[]`, a list over several lines, or no `[ignore]` table the policy still works but `always` is not offered.

`hold_until_named = true` closes the gap in loops that arm auto-merge inside the pipeline: the `itemator` job exits with an error while any kept extra has no name, so GitLab cannot merge before the card exists. The job passes again when the reaction account has posted its "Every extra has an answer" summary for the current head commit; after the last name, retry the `itemator` job (the card says so). Only a note from the exact reaction account counts (`ai-itemator-react-gitlab-ai-hackathon` here; set the CI variable `ITEMATOR_REACT_BOT` to your own account's username), the check fails closed if the notes cannot be read, and it needs the project to require a successful pipeline before merging.

## 6. The decision log (optional)
Copy the `decision-log` job from `.gitlab-ci.yml` and `itemator/decisions.py`. On a tag it reads the merge requests merged since the previous tag, takes each one's "Every extra has an answer" summary note, and writes a "Decisions in <tag>" section into that release's description (it creates the release if there is none). Run by hand on the default branch it reports the last thirty days and writes `decisions.md` and `decisions.json` as job artifacts. It uses the job token, reads merge requests and notes, and writes nothing else. Only notes from the exact reaction account are believed (`ai-itemator-react-gitlab-ai-hackathon` here; set `ITEMATOR_REACT_BOT` to your own account's username), because anyone can comment on a public project.

## What to expect
Open a merge request that links an issue. When its pipeline finishes, the card appears with one thread per extra. Answer in a thread with the extra's exact name, `split`, `remove` or `not an extra`, then mention the reaction account (or mark the merge request ready). Anything the issue already names is not an extra: to approve an extra in advance, say it in the issue.

## What we did not test
A second approver, a project other than this one, GitLab Self-Managed, and an organisation-wide compliance pipeline. The job definition itself still comes from the merge request unless you pull it in from a protected include.
