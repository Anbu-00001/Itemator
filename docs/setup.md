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

## What to expect
Open a merge request that links an issue. When its pipeline finishes, the card appears with one thread per extra. Answer in a thread with the extra's exact name, `split`, `remove` or `not an extra`, then mention the reaction account (or mark the merge request ready). Anything the issue already names is not an extra: to approve an extra in advance, say it in the issue.

## What we did not test
A second approver, a project other than this one, GitLab Self-Managed, and an organisation-wide compliance pipeline. The job definition itself still comes from the merge request unless you pull it in from a protected include.
