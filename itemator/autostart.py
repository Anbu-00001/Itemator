"""Start the card flow on a merge request a coding agent opened. GitLab will not let a trigger start a flow for one ("A
non-human user such as a bot user, service account user, or another flow, cannot activate a trigger", Triggers page), so
without this a person has to mark the agent's draft ready. The CI job calls the flows API (POST /ai/duo_workflows/workflows,
GA in GitLab 19.5) with a person's token and, if GitLab drops the session, restarts it once (.../:id/restart).
The card's own duplicate check makes a second start harmless. It stops for good at the hackathon deadline.
Standard library only; no model.

usage: python3 -m itemator.autostart    (in the itemator-autostart CI job; reads CI variables)"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEADLINE = datetime(2026, 10, 27, 13, 0, tzinfo=timezone.utc)   # nothing may run by itself after the hackathon closes
AGENT_BRANCH = "duo/"        # GitLab's Developer Flow opens its merge requests from duo/ branches
POLL, WAIT = 20, 480         # seconds between status reads, and in all
ENDED = {"FINISHED", "STOPPED"}


# ---------------------------------------------------------------- pure parts (tests/test_autostart.py)

def should_start(env: dict, now: datetime) -> tuple[bool, str]:
    """Whether this pipeline starts the card, and why not when it does not."""
    if now >= DEADLINE:
        return False, "the hackathon deadline has passed"
    if env.get("ITEMATOR_AUTOSTART", "on").strip().lower() == "off":
        return False, "ITEMATOR_AUTOSTART is off"
    if env.get("CI_PIPELINE_SOURCE") != "merge_request_event" or not env.get("CI_MERGE_REQUEST_IID", "").isdigit():
        return False, "not a merge request pipeline"
    if not env.get("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME", "").startswith(AGENT_BRANCH):
        return False, "not an agent's branch (a person's merge request starts the card through its trigger)"
    if not env.get("ITEMATOR_CARD_CONSUMER_ID", "").isdigit():
        return False, "ITEMATOR_CARD_CONSUMER_ID is not set"
    if not env.get("ITEMATOR_START_TOKEN"):
        return False, "ITEMATOR_START_TOKEN is not set"
    return True, "agent merge request"


def payload(env: dict) -> dict:
    iid = env["CI_MERGE_REQUEST_IID"]
    return {"project_id": int(env["CI_PROJECT_ID"]), "ai_catalog_item_consumer_id": int(env["ITEMATOR_CARD_CONSUMER_ID"]),
            "merge_request_id": int(iid), "goal": iid, "start_workflow": True, "environment": "ambient"}


def next_step(status: str | None, restarted: bool) -> str:
    """wait, done, restart (once, after GitLab fails the session) or give_up."""
    if status in ENDED:
        return "done"
    if status == "FAILED":
        return "give_up" if restarted else "restart"
    return "wait"


# ---------------------------------------------------------------- the calls

def _call(url: str, token: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), method="POST",
                                 headers={"PRIVATE-TOKEN": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null") or {}


def _status(api: str, token: str, path: str, wid: int) -> str | None:
    q = ('{ duoWorkflowWorkflows(projectPath: %s, workflowId: "gid://gitlab/Ai::DuoWorkflows::Workflow/%d") { nodes { status } } }'
         % (json.dumps(path), wid))
    nodes = (_call(api.rsplit("/api/v4", 1)[0] + "/api/graphql", token, {"query": q}).get("data") or {}) \
        .get("duoWorkflowWorkflows", {}).get("nodes") or []
    return nodes[0]["status"] if nodes else None


def main(env=None, now=None, sleep=time.sleep) -> int:
    env = dict(os.environ) if env is None else env
    go, why = should_start(env, now or datetime.now(timezone.utc))
    print(f"itemator-autostart: {'starting the card' if go else 'not starting'}: {why}")
    if not go:
        return 0
    api, token = env["CI_API_V4_URL"], env["ITEMATOR_START_TOKEN"]
    try:
        wid = _call(f"{api}/ai/duo_workflows/workflows", token, payload(env))["id"]
        print(f"itemator-autostart: session {wid} started")
        restarted, waited = False, 0
        while waited < WAIT:
            sleep(POLL)
            waited += POLL
            step = next_step(_status(api, token, env["CI_PROJECT_PATH"], wid), restarted)
            if step == "done" or step == "give_up":
                print(f"itemator-autostart: session {wid} {'ended' if step == 'done' else 'failed again; a person can mark the draft ready'}")
                return 0
            if step == "restart":
                wid, restarted = _call(f"{api}/ai/duo_workflows/workflows/{wid}/restart", token, {})["id"], True
                print(f"itemator-autostart: GitLab failed the session; restarted it once as {wid}")
        print(f"itemator-autostart: session {wid} still running after {WAIT} s; leaving it")
    except (urllib.error.URLError, KeyError, ValueError) as e:      # the card can still start when a person marks the draft ready
        print(f"itemator-autostart: could not start the card ({e}); a person can mark the draft ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
