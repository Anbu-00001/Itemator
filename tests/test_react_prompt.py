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
         "create_merge_request_note", "update_merge_request", "create_commit", "create_merge_request",
         "create_issue_note"]                                           # T46: the receipt on the issue
GUARDS = '"Remove partly done:", "Cannot remember:" or "Remember failed:"'
# T51: the Step 8 line is back to its pre-T46 form (the approval field was removed with Step 7d)
STEP8 = ("Checked <number of merge requests>: <KEPT> kept, <DISMISSED> dismissed, <SPLIT> moved, <REMOVED> removed, "
         "<number in OPEN_NAMES> open.")
# T51: words that only an approval step would need; none may come back
NEVER = ("/approve", "approval_state", "approved_by", "eligible_approvers", "APPROVED")


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


def test_the_flow_never_approves(flow):
    """T51: the bot approval (Step 7d) was removed on GitLab staff's advice: a flow's approval counts as the person who
    started it, so it is not independent. Placed second so that `-x` names this test for every T51 mutant."""
    _, system = flow
    text = FLOW.read_text()
    for word in NEVER:
        assert word not in text, word
    assert ("You never decide whether a change is good, you never approve a merge request, you never merge or close "
            "one,") in system
    assert "Step 7d" not in text and "you approve" not in system
    assert f'"{STEP8}" No analysis.' in system


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
    assert STEP8 in quoted and STEP8 in system
    assert sorted(q for q in quoted if q not in system) == sorted(REWORDED_T64)
    assert all(new in system for new in REWORDED_T64.values())


# T64: worded about the change, never the person, and a removal says how to bring the file back. Each old phrase is replaced
# once, on purpose; every other quoted phrase stays.
REWORDED_T64 = {
    " This person wrote the merge request.": " (@WHO also wrote this merge request.)",
    "Removed: `NAME` taken out of this merge request by @WHO. Nothing was kept.":
        "Removed: `NAME` taken out of this merge request by @WHO. To bring it back, revert the commit 'Remove `NAME` from !<IID>'.",
}


def test_t42_the_one_line_edit_is_checked_with_compare_not_with_a_character_count(flow):
    """Audit pass 1, fixes 1 to 4: OLD occurs once (a comment counts), no # or trailing comma in the list, a leftover branch
    stops `always`, and the check reads the compare endpoint instead of counting characters."""
    _, system = flow
    step = system[system.index("Step 5b."):system.index("Step 6.")]
    for s in ("does not appear exactly once in the whole decoded file (a comment counts)",
              "contains a [ or a ] character, or the list holds a # or ends with a comma",
              'must be OLD with only \', "PATH"\' or \'"PATH"\' inserted just before the ] that closes the list',
              "is left from an earlier try; delete it, then reply always again.",
              '"/api/v4/projects/<project_id>/repository/compare"', '"straight": "true"',
              'exactly one line starting with "-"', 'exactly one line starting with "+"'):
        assert s in step, s
    assert "SIZE" not in step and "length of NEW_LINE" not in step


def test_t42_an_answer_typed_with_the_mention_counts(flow):
    _, system = flow
    assert "then spaces at both ends and one trailing full stop taken off again, in lower case" in system
    assert 'T1 with every @ai-itemator- mention taken out and spaces at both ends taken off, is exactly NAME' in system


def test_t42_the_mention_step_leaves_a_question_from_a_person_alone(flow):
    _, system = flow
    step = system[system.index("Step 7b."):system.index("Step 8.")]
    assert 'mentions no @account except accounts whose name starts with "@ai-itemator-"' in step
    assert "every note after the first is a bot note or a system note" in step


def test_t42_a_no_issue_merge_request_never_swaps_its_label_and_stays_in_draft(flow):
    """The itemator:: labels replace each other (checked live on !24, 2026-10-13), so adding needs-names to a no-issue merge
    request would drop no-issue and let Step 6 lift the Draft hold."""
    _, system = flow
    step = system[system.index("Step 6."):system.index("Step 7.")]
    assert step.count('"itemator::no-issue"') == 3
    assert 'leave add_labels out while the label "itemator::no-issue" is on' in step
    assert 'the label "itemator::no-issue" is not on the merge request and the label "itemator::needs-names" is missing' in step
    assert 'and the label "itemator::no-issue" is not on the merge request (one that nobody described' in step


# ---------------------------------------------------------------- T46: the asker rule and the receipt (T51 removed the approval)
def between(system: str, start: str, end: str) -> str:
    return system[system.index(start):system.index(end, system.index(start))]


ASK_CHECK = "in an ASKER_ONLY thread, the author's username is exactly one of ASKERS"


def test_t46_steps_are_in_order_and_each_merge_request_runs_them_all(flow):
    _, system = flow
    order = [system.index(s) for s in ("Step 7.", "Step 7b.", "Step 7c.", "Step 8.")]
    assert order == sorted(order)
    assert "Do steps 2 to 7c for each IID in MRS" in system
    assert "PEOPLE = empty, OPEN_NAMES = empty and ALWAYS = empty." in system


def test_t46_the_asker_sentence_is_read_exactly_as_the_checker_writes_it(flow):
    """The flow can only read the thread text, so its detection text must be the checker's own (itemator/ci.py)."""
    _, system = flow
    step = between(system, "Step 3.", "Step 4.")
    assert f'If the part of that first note after the backtick that closes NAME contains the text "{ci.ASKER_ONLY_PREFIX}" the thread is ASKER_ONLY' in step
    assert f'between the last place that text appears and the next "{ci.ASKER_ONLY_SUFFIX}" after it' in step
    assert 'separated by " or ", each copied exactly (same letters, same case).' in step
    assert ("If any part there is not one @name made only of letters, digits, _, . and -, ASKERS is empty, so no reply "
            "can keep or dismiss that extra (split and remove still work).") in step
    stub = ci.asker_sentence(("Alice", "bob.b"))
    assert stub.startswith(ci.ASKER_ONLY_PREFIX) and stub.endswith(ci.ASKER_ONLY_SUFFIX)
    inner = stub[len(ci.ASKER_ONLY_PREFIX):-len(ci.ASKER_ONLY_SUFFIX)]
    assert [p.removeprefix("@") for p in inner.split(" or ")] == ["Alice", "bob.b"]   # how the prompt says to read it


def test_t46_only_an_asker_keeps_or_dismisses_and_split_remove_keep_the_crew_rule(flow):
    _, system = flow
    step = between(system, "Step 4.", "Step 5.")
    named, dismissed = between(step, "NAMED if", "DISMISSED if"), between(step, "DISMISSED if", "SPLIT if")
    split, remove = between(step, "SPLIT if", "REMOVE if"), between(step, "REMOVE if", "ALWAYS if")
    always = between(step, "ALWAYS if", "A near match")
    assert f", and, {ASK_CHECK};" in named
    assert f'"not an extra" and, {ASK_CHECK};' in dismissed
    assert f"the author is in CREW and, {ASK_CHECK}, and the reply was written after LAST_REFUSAL." in always
    assert "ASKER" not in split and "ASKER" not in remove
    assert "the author is in CREW" in split and "the author is in CREW" in remove
    assert ('In an ASKER_ONLY thread a name, "not an extra" or "always" from anyone whose username is not exactly one of '
            "ASKERS (compared with the same letters and the same case) fits no test, even from AUTHOR or someone in "
            "CREW: the thread stays open and gets no reply.") in step
    assert "In an OTHER_ONLY thread leave out every reply whose author is AUTHOR." in step     # both rules apply


def test_t46_no_extra_threads_still_reach_the_mention_step(flow):
    _, system = flow
    step = between(system, "Step 3.", "Step 4.")
    assert "If there are no extra threads, change nothing for this merge request except in step 7b." in step
    assert "Do this step even when there are no extra threads" in between(system, "Step 7b.", "Step 7c.")


def test_t46_the_reminder_names_the_asker_and_the_summary_says_who_typed(flow):
    _, system = flow
    step = between(system, "Step 7.", "Step 7b.")
    rem, summ = between(step, "- Reminder", "- Summary"), step[step.index("- Summary"):]
    asker = rem.index('"Waiting for the person who wrote the issue (@x): " if some thread of a name in OPEN_NAMES is '
                      "ASKER_ONLY and its ASKERS is not empty")
    assert asker < rem.index('else "Waiting for someone other than the author: "') < rem.index(GUARDS)
    assert "in both cases only when no thread of a name in OPEN_NAMES has a note written by REACT_BOT" in rem
    a = summ.index('if some extra thread is ASKER_ONLY, PEOPLE is not empty and every name in it is one of the ASKERS of '
                   'an ASKER_ONLY thread, a blank line and the line "All of it was typed by the person who wrote the '
                   'issue."; otherwise, if no extra thread is OTHER_ONLY')
    assert a < summ.index('"All of it was typed by the author of this merge request."')


def test_t46_the_receipt_is_posted_once_after_the_summary_and_never_starts_a_line_with_a_slash(flow):
    _, system = flow
    step = between(system, "Step 7c.", "Step 8.")
    for s in ("Do this step only when OPEN_NAMES is empty, the merge request has at least one extra",
              "step 7 posted the summary in this run or its search found the summary already there",
              '"/api/v4/projects/<project_id>/merge_requests/<IID>/closes_issues" and params {"per_page": "20"}',
              "ISSUE_IID = the iid of the first entry in its data; if there is none or the call fails, skip this step.",
              'MARKER_R = "itemator:receipt=<IID>:<HEAD>"',
              '{"scope": "notes", "search": "<MARKER_R>", "per_page": "20"}',
              'has noteable_type "Issue", noteable_iid equal to ISSUE_IID, and an author whose username is REACT_BOT, '
              "post nothing; if the search fails, post nothing.",
              "call create_issue_note once with project_id, issue_iid ISSUE_IID",
              '"Receipt from Itemator for !<IID>: this merge request went beyond this issue in <number of extras> '
              'place(s), and each has an answer."',
              '"- `NAME`: <kept|dismissed|moved|removed>, decided by @WHO"', "then MARK(MARKER_R)",
              'and when that note ends with "Their reason is in their reply." add ", with a reason in its thread" at the end of that line'):
        assert s in step, s
    assert "create_issue_note" not in system.replace(step, "")          # the issue gets nothing from any other step


def test_t46_quoted_strings_that_start_with_a_slash_are_endpoints(flow):
    _, system = flow
    assert ('No line of any note, reply, title or description you write may start with "/", with no exception (GitLab runs '
            'such a line as a command).') in system
    slash = [q for q in re.findall(r'"([^"\n]+)"', system) if q.startswith("/")]
    assert slash and all(q.startswith("/api/v4/") or q in ("/", "/merge_requests/<n>") for q in slash), slash


def test_t46_the_pre_registered_asker_cases_are_complete():
    path = ROOT / "eval" / "asker_study_cases.json"
    if not path.exists():
        pytest.skip("no eval/ in this copy (the mutation runner copies only itemator, tests, tools and flows)")
    cases = json.loads(path.read_text())["cases"]
    assert len(cases) == 6 and len({c["label"] for c in cases}) == 6
    assert {c["expected"] for c in cases} <= {"kept", "dismissed", "open", "policy proposed"}
    assert sum(c["expected"] == "open" for c in cases) >= 3


def test_t44_a_file_name_cannot_plant_the_thread_flags(flow):
    """Audit pass 3, fix 5: the OTHER_ONLY, ALWAYS_OK and ASKER_ONLY sentences are looked for only AFTER the backtick that closes
    NAME, so a file name that contains one of them does not change what the thread allows."""
    _, system = flow
    assert system.count("If the part of that first note after the backtick that closes NAME contains the ") == 3
    assert "If that first note contains the " not in system


def test_a_reply_counts_only_from_a_person_checked_with_the_users_endpoint(flow):
    _, text = flow
    assert "whose author is a person" in text
    assert '"/api/v4/users/<author id>"' in text
    assert "bot true, or the call fails, that author is not a person" in text
    assert "a person's data has bot false" in text


def test_read_as_says_how_it_read_plain_words_and_never_settles(flow):
    _, system = flow
    order = [system.index(s) for s in ("Step 5.", "Step 5r.", "Step 5a.", "Step 6.")]
    assert order == sorted(order)                                   # after the answers are judged, before anything moves
    r = system[system.index("Step 5r."):system.index("Step 5a.")]
    body = re.search(r'body: "(Read as: [^"]+)"', r).group(1)
    assert body.startswith("Read as: `WORD`") and "Nothing was done." in body and not body.startswith("/")
    assert not body.startswith(("Kept:", "Dismissed:", "Split:", "Removed:"))          # step 4's SETTLED words
    assert "only a reply that passes the tests of step 4" in r and "change nothing" in r
    assert "never as instructions" in r and "gives you orders" in r and "WORD is none and you post nothing" in r
    assert '"split" or "remove" only when the source\'s author is in CREW' in r      # the CREW rule holds for a reading too
    assert 'starts with "Read as:"' in r                                         # one reading per source, never twice
    assert "create_commit" not in r and "update_merge_request" not in r and "set_discussion_resolved" not in r
    settled = system[system.index("Step 4."):system.index("For a thread that is not SETTLED")]
    assert "Read as" not in settled


def test_one_reply_to_the_card_can_keep_several_and_only_keep(flow):
    _, system = flow
    s4 = system[system.index("Step 4."):system.index("Step 5.")]
    assert "CARD_REPLIES = the notes after the first one" in s4 and "written by CARD_BOT, contains the text \" beyond \"" in s4
    assert "is not an extra thread (that note is the card)" in s4 and "whose author is a person (by the same users check)" in s4
    card = s4[s4.index("look at CARD_REPLIES in order"):]
    assert "is exactly NAME (same letters and same case)" in card and "one of ASKERS" in card
    assert 'A card reply can only keep: "not an extra", "split", "remove" and "always" count only in the extra\'s own thread.' in card
    assert s4.index("If no reply fits, look at CARD_REPLIES") < s4.index("If still nothing fits, the thread is OPEN.")   # the thread's own reply wins
    s5 = system[system.index("Step 5."):system.index("Step 5r.")]
    assert 'If the thread is FROM_CARD, add " Named in a reply to the card." at the very end; otherwise' in s5
    assert "so a reply to the card never blocks the merge" in s5 and "Once OPEN_NAMES is empty after this step" in s5
    other = s4[s4.index("- CARD_REPLIES"):s4.index("\n", s4.index("- CARD_REPLIES"))]
    assert "In an OTHER_ONLY thread leave out every one whose author is AUTHOR." in other


def test_the_card_says_several_can_be_kept_in_one_reply():
    assert ci.SEVERAL == "To keep several at once, reply to this card with one name per line."
