"""T40: the react prompt (flows/itemator_react.yml) carries the `always` step (5b) and the mention-thread step (7b),
keeps every earlier reply phrase, parses as YAML and stays under 40 KiB. The prompt is read, never run: no network."""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from itemator import ci

ROOT = pathlib.Path(__file__).resolve().parent.parent
FLOW = ROOT / "flows" / "itemator_react.yml"
BEFORE_T40 = "772a677"
TOOLS = ["get_merge_request", "gitlab_api_get", "reply_to_discussion", "set_discussion_resolved",
         "create_merge_request_note", "update_merge_request", "create_commit", "create_merge_request"]
GUARDS = '"Remove partly done:", "Cannot remember:" or "Remember failed:"'


def parse(text: str):
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        pass
    py = shutil.which("python3")
    if not py or subprocess.run([py, "-I", "-c", "import yaml"], capture_output=True).returncode:
        pytest.skip("no YAML parser here")
    r = subprocess.run([py, "-I", "-c", "import json, sys, yaml; print(json.dumps(yaml.safe_load(sys.stdin.read())))"],
                       input=text, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def flow():
    if not FLOW.exists():
        pytest.skip("no flows/ in this copy")
    doc = parse(FLOW.read_text())
    return doc, doc["prompts"][0]["prompt_template"]["system"]


def test_yaml_parses_and_stays_under_40_kib(flow):
    doc, system = flow
    assert len(FLOW.read_bytes()) < 40 * 1024 and len(system.encode()) < 40 * 1024
    assert doc["components"][0]["toolset"] == TOOLS
    assert system.isascii()


def test_the_new_words_are_there(flow):
    _, system = flow
    for word in ("always", "Cannot remember:", "Remember failed:", "@ai-itemator-react", ".itemator.toml",
                 "Step 5b.", "Step 7b.", "ALWAYS_OK", "ALWAYS"):
        assert word in system, word
    order = [system.index(s) for s in ("Step 5.", "Step 5a.", "Step 5b.", "Step 6.", "Step 7.", "Step 7b.", "Step 8.")]
    assert order == sorted(order)
    assert ci.ALWAYS in system                       # how the flow tells an offered thread from any other


def test_every_refusal_list_carries_the_new_guard_words(flow):
    _, system = flow
    assert system.count('"Remove partly done:"') == system.count(GUARDS) == 2      # LAST_REFUSAL and the reminder


def test_the_always_replies_are_exactly_the_brief(flow):
    _, system = flow
    for s in ("Cannot remember: the target branch has no .itemator.toml.",
              "Cannot remember: .itemator.toml has no single paths line to extend.",
              "Cannot remember: the policy already lists PATH.",
              "Cannot remember: the policy already lists many paths.",
              "Cannot remember: the branch is in a fork.",
              "Remember failed: the new branch does not hold exactly the one-line change; nothing else was changed.",
              '"Policy: stop asking about PATH"',
              '"Proposed by @WHO from !<IID>. Merging this stops the questions about PATH on later merge requests; it is '
              "a team decision, and the policy file is read from the target branch, so this merge request itself will "
              'ask for a name. Close it to keep asking."',
              '"Kept: `NAME`, kept by @WHO. Policy change proposed in !<NEW>: merging it stops the questions about `PATH`."',
              '"- `NAME`: kept, and a policy change was proposed in !<NEW>, by @WHO"',
              "itemator/always-<IID>-", 'paths = ["PATH"]', 'paths = ["a", "PATH"]'):
        assert system.count(s) >= 1, s


def test_the_mention_step_resolves_only_human_mention_threads(flow):
    _, system = flow
    step = system[system.index("Step 7b."):system.index("Step 8.")]
    for s in ("@ai-itemator-react", "is not a bot note", "resolvable", "not resolved", "set_discussion_resolved",
              "resolved true", "no extra threads", "Never", "step 3"):
        assert s in step, s
    assert "resolved false" not in step and "reply_to_discussion" not in step


def test_settled_reads_who_from_the_always_reply():
    """Step 4 takes WHO after the last "by @" in the first line; a PATH has no space, so it cannot hold "by @"."""
    for path in ("conf/a@b+c.yml", ".gitlab-ci.yml", "by@x/y.ini"):
        line = (f"Kept: `{path}`, kept by @alice. Policy change proposed in !31: merging it stops the questions "
                f"about `{path}`.")
        assert re.match(r"[A-Za-z0-9_.-]*[A-Za-z0-9_]", line.rsplit("by @", 1)[1]).group(0) == "alice"
        assert line.startswith("Kept:")


def test_every_earlier_quoted_phrase_is_kept(flow):
    _, system = flow
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{BEFORE_T40}:flows/itemator_react.yml"],
                       capture_output=True, text=True)
    if r.returncode:
        pytest.skip(f"commit {BEFORE_T40} is not in this clone")
    old = parse(r.stdout)["prompts"][0]["prompt_template"]["system"]
    quoted = set(re.findall(r'"([^"\n]{3,})"', old))
    assert len(quoted) > 60
    assert sorted(q for q in quoted if q not in system) == []
