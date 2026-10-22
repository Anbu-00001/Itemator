# Use Itemator in your own project

We created the flows in this project through GitLab's GraphQL API; the menu path below (AI > Flows) is the documented one and is untested by us. We installed it once more, in [second-project](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/39194174/second-project), by the same steps without the policy (see [what we did not test](#what-we-did-not-test)).

**You need:** GitLab Premium or Ultimate with the Duo Agent Platform and custom flows turned on (Ultimate for the policy below: pipeline execution policies are Ultimate only), the Owner role once to link the policy project, a public project (in a private one the job cannot read the issue, see [limits](limits.md)), a role that can create AI flows and triggers (ours was a custom Developer + AI role), and a Python 3.12 runner image for the CI job.

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
In the project, open **AI** > **Flows** > **New flow** (menu names vary by GitLab version), choose **Private**, and paste the contents of [flows/itemator_card.yml](../flows/itemator_card.yml). Do the same for [flows/itemator_react.yml](../flows/itemator_react.yml). Then **enable** each flow in your project (we enabled ours through the API, not this menu, so the exact button is untested here). A private flow made in another project cannot be enabled in yours (GitLab says "Item is private in another project"): create your own copy. In our second project, enabling through the API with trigger types also created each flow's trigger, already on, and named each account after its flow (a flow called "Itemator react two" got `ai-itemator-react-two-<group>`). GitLab creates one service account per flow, named like `ai-itemator-card-<your top-level group>` and `ai-itemator-react-<your top-level group>`; check both exist under **Manage** > **Members** before you go on.

**Change two names in the reaction flow, and set one variable.** Its prompt names the two accounts exactly (`CARD_BOT` and `REACT_BOT`): replace them with the account names GitLab created in your group, so only notes from those two accounts count as cards or settled answers. Then put your reaction account's username into `ci/itemator-job.yml` (two lines name it, the `variables:` entry and the `export` line: change both; the injected job ignores a project variable on purpose) and into the CI/CD variable `ITEMATOR_REACT_BOT` (**Settings** > **CI/CD** > **Variables**), which only the `decision-log` job reads. If you skip a step, no card or answer is recognised.

## 3. The triggers
In **AI** > **Triggers** > **New flow trigger**, create two triggers. Both are off until you switch them on, and every one needs a person's action to fire (a bot cannot start a trigger, which is also why the flows cannot start each other). We created ours with a custom "Developer + AI" role; on a normal install you need Maintainer.
- Card flow (service account: the card account): event **Pipeline** (statuses Passed and Failed, source merge request) and event **Assign reviewer**. The project must sit under a top-level group, because service accounts are created per group.
- Reaction flow (service account: the reaction account): events **Mention**, **Merge request ready** (called **Marked ready** under **Merge request** in newer GitLab versions), and **Merge request** with the **Approved** action (we never tested Approved).

## 4. Make the threads a lock (needs the Maintainer role; without it nothing blocks the merge)
In **Settings** > **Merge requests**, turn on **All threads must be resolved**. Until then an unnamed extra puts the merge request in Draft but does not stop the merge button.

## 4b. The skills (optional)
Copy the [skills/](../skills/) folder to the root of your repository. GitLab's Developer Flow read `stay-inside-the-issue` from there with no other setup in our one run; `answer-an-itemator-card` lets an agent explain a card and its answers to a person who asks.

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

### An issue can declare its own scope (optional)

An issue that needs to be exact can say what a change may touch, in a fenced block anywhere in its description:

    ```itemator-scope
    paths: src/parser/**, tests/parser/**
    dependencies: none
    ```

`paths` are globs (`*` stays in one directory, `**` crosses them, a trailing `/` means everything under it); `dependencies` are package names, or `none`. Either line may be left out. What the block declares replaces the reading of the issue's words for that part: every changed file outside the paths is an extra named by its path, and every new dependency not on the list is an extra even when the issue's words contain its name. Extras on files inside the paths count as asked for, except a new dependency (only the list allows one), an agent instruction file, and a binary or large file. The card says when a block was used. Without a block nothing changes (`itemator/scope.py`).

## 5b. Another scope checker (optional)

If you already run a scope checker, or want one that names more files than Itemator's rules, run it in an earlier job and pass its JSON output as an artifact. Set `ITEMATOR_OTHER_CHECKER` to that file's path in the Itemator job. Each changed file it names, and the rules did not, becomes an extra labelled "named by another checker" with the checker's own reason, and gets the same thread, typed answer, hold and log entry. It reads Overreach's `--json` output, the Scope Creep Detector's `--json` output, and a plain `{"tool": "name", "files": [{"path": "...", "why": "..."}]}`. An issue with an `itemator-scope` block is left to that block. A file that cannot be read is said on the card, and only Itemator's own rules run. See [itemator/other.py](../itemator/other.py).

```yaml
scope-check:
  stage: test
  image: node:lts-alpine
  variables: { OVERREACH_TELEMETRY: "off" }
  script:
    - git fetch origin "$CI_MERGE_REQUEST_TARGET_BRANCH_NAME"
    - git diff "origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME...HEAD" > change.diff
    - npx -y overreach@0.9.0 -p "$CI_MERGE_REQUEST_TITLE" --diff change.diff --json > overreach.json || true
  artifacts: { paths: [overreach.json] }
  rules: [{ if: $CI_PIPELINE_SOURCE == "merge_request_event" }]
```

Then give the Itemator job `needs: [scope-check]` and `ITEMATOR_OTHER_CHECKER: overreach.json`. We have not run this job in a pipeline; the parsing is covered by tests/test_other.py.

## 6. The decision log (optional)
**Read other projects' answers (optional).** Set `ITEMATOR_SHARED_ANSWERS` to the public answer logs of other projects (their `answers/answers.json` on Pages, separated by spaces). When an extra here has the same name as one a person answered there, the thread adds "Decided in group/project: ... on group/project!N". A log is used only when its hash chain holds; it is a fact beside the question, and a person here still types the answer.

Copy the `decision-log` job from `.gitlab-ci.yml` and `itemator/decisions.py`. On a tag it reads the merge requests merged since the previous tag, takes each one's "Every extra has an answer" summary note, and writes a "Decisions in <tag>" section into that release's description (it creates the release if there is none). Run by hand on the default branch it reports the last thirty days and writes `decisions.md` and `decisions.json` as job artifacts. It uses the job token, reads merge requests and notes, and writes nothing else. Only notes from the exact reaction account are believed (`ai-itemator-react-gitlab-ai-hackathon` here; set `ITEMATOR_REACT_BOT` to your own account's username), because anyone can comment on a public project.

To see what your merged merge requests carried before you installed Itemator, copy the `scan-history` job from `.gitlab-ci.yml` (it needs `itemator/`). Run it by hand on the default branch; it reads the last fifty merged merge requests (set `SCAN_LAST` for another number) and writes `scan.md` and `scan.json`. It uses the job token, reads only, and needs a full clone, which the job asks for with `GIT_DEPTH`. It was run on a public project only: GitLab's job token can read merge requests but not issues, so in a private project the issues cannot be read this way (the same holds for the `itemator` job; see Known limits in the README).

## What to expect
Open a merge request that links an issue. When its pipeline finishes, the card appears with one thread per extra. Answer in a thread with the extra's exact name, `split`, `remove`, `always` (when the thread offers it) or `not an extra`, then mention the reaction account (or mark the merge request ready). Anything the issue already names is not an extra: to accept an extra in advance, say it in the issue.

## What we did not test
A second approver, GitLab Self-Managed, and an organisation-wide compliance pipeline. A project other than this one was tried once: [second-project](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/39194174/second-project), installed by the CI job section above without the policy, ran the job on its first merge request and named the extra with what this project had decided about it ([record](../results/second_project_v1.json)). Its card flow was then created from `flows/itemator_card.yml` and posted the thread with that sentence ([thread](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/39194174/second-project/-/merge_requests/1#note_4065276875), [record](../results/second_project_card_v1.json)). Its reaction flow, created the same way with the two names changed, then took an answer there: `remove` took the file out with a commit, resolved the thread and lifted Draft ([summary](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/39194174/second-project/-/merge_requests/1#note_4065942500), [record](../results/second_project_react_v1.json)). If you do not use the policy above, the job definition itself comes from the merge request.

## Names and places to change in a fork
| Where | What to change |
|---|---|
| `flows/itemator_card.yml`, `flows/itemator_react.yml` | the two service account names `CARD_BOT` and `REACT_BOT` in the prompts |
| `ci/itemator-job.yml` (and the copy in the policy project) | the reaction account's username, in the `variables:` entry and the `export` line |
| `.gitlab-ci.yml`, job `policy-job-in-sync` | delete the job, or change the project id in its URL to your policy project's id: it compares the repository copy of the job file with the copy in our policy project and fails in a fork |
| `.gitlab-ci.yml`, jobs `publish-package`, `shipped-page` | optional: they record deployments and publish the page of what shipped; delete them if you do not want that |
| policy project, `policy.yml` | `project:` must name the policy project itself, and the file `ci/itemator-job.yml` must be in it |

Check it worked: open a merge request, and its pipeline must show a job `itemator` in the stage `.pipeline-policy-post`.
