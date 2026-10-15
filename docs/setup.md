# Use Itemator in your own project

We created the flows in this project through GitLab's GraphQL API; the menu path below (AI > Flows) is the documented one and is untested by us. We have not installed Itemator in a second project.

**You need:** GitLab with the Duo Agent Platform and custom flows turned on, a role that can create AI flows and triggers (ours was a custom Developer + AI role), and a Python 3.12 runner image for the CI job.

## 1. The CI job
1. Copy the `itemator/` folder to the root of your repository.
2. Copy [ci/itemator-job.yml](../ci/itemator-job.yml) into your repository. It holds the `itemator` job, which runs only in merge request pipelines. Do not put the job in your `.gitlab-ci.yml`: the policy section further down injects it, so a merge request cannot edit, delete or skip it. If you cannot use a policy, paste the job into `.gitlab-ci.yml` instead and drop its `stage:` line; the job then comes from the merge request's own file, which is a gap (see the end of this page).
3. Optional: copy [.itemator.toml](../.itemator.toml) and read its comments. The job reads that file, and runs the checker itself, from the branch the merge request targets, so a merge request cannot change the rules it is judged by.

## The policy: inject the job (recommended)
This is what keeps a merge request from removing the check. Our project does it; the steps below are the ones we ran.
1. Make a small separate project in the same group (public or internal; it holds one file) and add `.gitlab/security-policies/policy.yml` to its default branch:
```yaml
pipeline_execution_policy:
  - name: itemator
    description: Injects the itemator job into every merge request pipeline.
    enabled: true
    pipeline_config_strategy: inject_policy
    suffix: never
    content:
      include:
        - project: <group>/<your-project>
          file: ci/itemator-job.yml
    policy_scope: {}
```
2. Link it: in your project, **Secure** > **Policies** > **Edit policy project** (the name GitLab's documentation gives; we did not click it) (the documented path; we linked through the GraphQL mutation `securityPolicyProjectAssign`). You need the Owner role, or a custom role with the "link to a security policy project" ability (the organisers added it to ours).
3. Check it: open a merge request. Its pipeline must show a job called `itemator` in the stage `.pipeline-policy-post`.

What we saw: the policy is read from the policy project's default branch, but GitLab's copy of it lags a few minutes behind a commit, so wait before testing a change. `suffix: never` makes a merge request that defines its own job named `itemator` fail at pipeline creation ("job names must be unique"), instead of running a fake next to the real one. A merge request that deletes your project's jobs, edits `ci/itemator-job.yml` or turns its pipeline off does not remove the injected job; we tried each of these against it in a pre-registered run; the numbers are in the README and in docs/how-it-works.md. Once a policy is linked, GitLab also requires the policy's pipeline to pass before a merge. Once, an unlink we sent took effect only the next morning: read the link back before you rely on it, and again before filming.

## 2. The two flows
In the project, open **AI** > **Flows** > **New flow** (menu names vary by GitLab version), choose **Private**, and paste the contents of [flows/itemator_card.yml](../flows/itemator_card.yml). Do the same for [flows/itemator_react.yml](../flows/itemator_react.yml). Then **enable** each flow in your project (we enabled ours through the API, not this menu, so the exact button is untested here). GitLab creates one service account per flow, named like `ai-itemator-card-<your top-level group>` and `ai-itemator-react-<your top-level group>`; check both exist under **Manage** > **Members** before you go on.

**Change two names in the reaction flow, and set one variable.** Its prompt names the two accounts exactly (`CARD_BOT` and `REACT_BOT`): replace them with the account names GitLab created in your group, so only notes from those two accounts count as cards or settled answers. Then put your reaction account's username into `ci/itemator-job.yml` (two lines name it, the `variables:` entry and the `export` line: change both; the injected job ignores a project variable on purpose) and into the CI/CD variable `ITEMATOR_REACT_BOT` (**Settings** > **CI/CD** > **Variables**), which only the `decision-log` job reads. If you skip a step, no card or answer is recognised.

## 3. The triggers
In **AI** > **Triggers** > **New flow trigger**, create two triggers. Both are off until you switch them on, and every one needs a person's action to fire (a bot cannot start a trigger, which is also why the flows cannot start each other). We created ours with a custom "Developer + AI" role; on a normal install you need Maintainer.
- Card flow (service account: the card account): event **Pipeline** (statuses Passed and Failed, source merge request) and event **Assign reviewer**. The project must sit under a top-level group, because service accounts are created per group.
- Reaction flow (service account: the reaction account): events **Mention**, **Merge request ready** (called **Marked ready** under **Merge request** in newer GitLab versions), and **Merge request** with the **Approved** action (we never tested Approved).

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
Open a merge request that links an issue. When its pipeline finishes, the card appears with one thread per extra. Answer in a thread with the extra's exact name, `split`, `remove`, `always` (when the thread offers it) or `not an extra`, then mention the reaction account (or mark the merge request ready). Anything the issue already names is not an extra: to accept an extra in advance, say it in the issue.

## What we did not test
A second approver, a project other than this one, GitLab Self-Managed, and an organisation-wide compliance pipeline. If you do not use the policy above, the job definition itself comes from the merge request.

## Names and places to change in a fork
| Where | What to change |
|---|---|
| `flows/itemator_card.yml`, `flows/itemator_react.yml` | the two service account names `CARD_BOT` and `REACT_BOT` in the prompts |
| `ci/itemator-job.yml` (and the copy in the policy project) | the reaction account's username, in the `variables:` entry and the `export` line |
| `.gitlab-ci.yml`, job `policy-job-in-sync` | delete the job, or change the project id in its URL to your policy project's id: it compares the repository copy of the job file with the copy in our policy project and fails in a fork |
| `.gitlab-ci.yml`, jobs `publish-package`, `shipped-page` | optional: they record deployments and publish the page of what shipped; delete them if you do not want that |
| policy project, `policy.yml` | `project:` must name the policy project itself, and the file `ci/itemator-job.yml` must be in it |

Check it worked: open a merge request, and its pipeline must show a job `itemator` in the stage `.pipeline-policy-post`.
