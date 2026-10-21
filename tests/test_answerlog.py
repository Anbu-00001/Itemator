"""The answer log. Notes come from fixtures and the published copy from a fake opener; nothing touches the network."""
import email.message
import io
import json
import urllib.error

import pytest

from itemator import answerlog as L

SHA = "b" * 40
URL = "https://gitlab.example/g/p"


def summary(*lines):
    return "Every extra has an answer.\n\n" + "\n".join(lines) + f"\n\n[//]: # (itemator:named={SHA})"


def note(nid, body, user="ai-itemator-react-gitlab-ai-hackathon", system=False, at="2026-10-13T10:00:00Z"):
    return {"id": nid, "body": body, "author": {"username": user}, "system": system, "created_at": at}


def fresh():
    return (L.entries_from(5, [note(11, summary("- `pandas`: kept, named by @alice"), at="2026-10-13T10:00:00Z")], URL)
            + L.entries_from(7, [note(12, summary("- `ci.yml`: removed from this merge request, by @bob"), at="2026-10-12T09:00:00Z")], URL))


def test_only_the_reaction_accounts_summaries_become_entries():
    notes = [note(1, summary("- `a`: kept, named by @alice")), note(2, summary("- `b`: kept, named by @alice"), user="mallory"),
             note(3, summary("- `c`: kept, named by @alice"), system=True), note(4, "Kept: `a`, named by @alice."), note("x", summary("- `d`: kept, named by @alice"))]
    got = L.entries_from(9, notes, URL)
    assert [(e["note"], [i["name"] for i in e["items"]]) for e in got] == [(1, ["a"])]
    assert got[0]["url"] == URL + "/-/merge_requests/9#note_1" and got[0]["commit"] == SHA and got[0]["iid"] == 9
    assert got[0]["items"] == [{"name": "a", "decision": "kept", "who": "alice", "ref": None}]
    assert len(got[0]["body_sha256"]) == 64


def test_a_chain_holds_and_any_change_breaks_it_where_it_happened():
    entries, changed = L.merge([], fresh())
    assert changed == [] and L.verify(entries) is None
    assert [e["note"] for e in entries] == [12, 11]                 # oldest first
    assert entries[0]["prev"] == L.START and entries[1]["prev"] == entries[0]["hash"]
    edited = json.loads(json.dumps(entries))
    edited[1]["items"][0]["decision"] = "removed"
    assert L.verify(edited) == 1
    edited = json.loads(json.dumps(entries))
    edited[0]["items"][0]["who"] = "mallory"
    assert L.verify(edited) == 0
    assert L.verify(entries[1:]) == 0                                # the first one taken out
    assert L.verify(list(reversed(entries))) == 0
    assert L.verify(entries + [{"note": 1}]) == 2


def test_a_rebuild_keeps_what_was_recorded_and_adds_only_new_notes_after_it():
    first, _ = L.merge([], fresh())
    later = L.entries_from(8, [note(10, summary("- `x`: kept, named by @carol"), at="2026-10-01T00:00:00Z")], URL)
    entries, changed = L.merge(first, fresh() + later)
    assert changed == []
    assert entries[:2] == first                                      # the same entries, the same hashes
    assert [e["note"] for e in entries] == [12, 11, 10]              # an older note found later still goes after them
    assert L.verify(entries) is None


def test_an_edited_or_missing_note_is_listed_and_its_entry_kept():
    first, _ = L.merge([], fresh())
    now = L.entries_from(5, [note(11, summary("- `pandas`: removed from this merge request, by @alice"))], URL)
    entries, changed = L.merge(first, now)
    assert entries == first
    assert {(c["note"], c["iid"], c["what"].split()[0]) for c in changed} == {(11, 5, "edited"), (12, 7, "not")}


class Opener:
    def __init__(self, code=200, body=b"", location=None):
        self.code, self.body, self.location = code, body, location

    def open(self, req, timeout=None):
        if self.code != 200:
            h = email.message.Message()
            if self.location:
                h["Location"] = self.location
            raise urllib.error.HTTPError(req.full_url, self.code, "x", h, None)
        return io.BytesIO(self.body)


@pytest.mark.parametrize("opener,want", [
    (Opener(404), []),
    (Opener(302, location="https://projects.gitlab.io/auth?domain=x"), []),
    (Opener(302, location="https://elsewhere.example/auth"), None),
    (Opener(302), None),
    (Opener(500), None),
    (Opener(200, b"not json"), None),
    (Opener(200, b'{"entries": 5}'), None),
    (Opener(200, b"[]"), None),
])
def test_only_a_missing_file_counts_as_no_log_yet(opener, want):
    assert L.published("https://site.example/answers/answers.json", opener) == want


def test_a_published_log_is_returned_whole():
    assert L.published("https://site.example/answers/answers.json", Opener(200, b'{"entries": [], "started": "s"}')) == {"entries": [], "started": "s"}


def test_the_page_escapes_names_and_says_when_the_chain_started():
    entries, _ = L.merge([], L.entries_from(5, [note(11, summary("- `<script>x</script>`: kept, named by @alice"))], URL))
    html = L.page({"entries": entries, "head": entries[-1]["hash"], "started": "2026-10-21T00:00:00Z",
                   "changed_after_recorded": [{"note": 3, "iid": 4, "what": "edited <b>"}]})
    assert "<script>x" not in html and "&lt;script&gt;x" in html
    assert "started 2026-10-21T00:00:00Z" in html and entries[-1]["hash"] in html
    assert "edited &lt;b&gt;" in html and "Changed after they were recorded" in html
    assert URL + "/-/merge_requests/5#note_11" in html and "1 answer in 1 summary note" in html


def test_verify_on_the_command_line(tmp_path):
    entries, _ = L.merge([], fresh())
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"entries": entries}))
    assert L.main(["--verify", str(good)]) == 0
    entries[1]["at"] = "2026-10-14T00:00:00Z"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"entries": entries}))
    assert L.main(["--verify", str(bad)]) == 1


ENV = {"CI_JOB_TOKEN": "t", "CI_API_V4_URL": "https://gitlab.example/api/v4", "CI_PROJECT_ID": "1", "CI_PROJECT_URL": URL,
       "CI_PAGES_URL": "https://site.example"}


def test_a_log_that_cannot_be_read_is_not_overwritten(tmp_path, monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    calls = []
    monkeypatch.setattr(L, "published", lambda url: calls.append(url))
    monkeypatch.setattr(L, "collect", lambda api, url: pytest.fail("must not read GitLab"))
    assert L.main(["--out", str(tmp_path / "out")]) == 1
    assert calls == ["https://site.example/answers/answers.json"] * 3 and not (tmp_path / "out").exists()


def test_a_broken_published_chain_is_not_built_on(tmp_path, monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    entries, _ = L.merge([], fresh())
    entries[0]["items"][0]["who"] = "mallory"
    monkeypatch.setattr(L, "published", lambda url: {"entries": entries})
    monkeypatch.setattr(L, "collect", lambda api, url: pytest.fail("must not read GitLab"))
    assert L.main(["--out", str(tmp_path / "out")]) == 1


def test_a_build_keeps_the_start_date_and_adds_the_new_notes(tmp_path, monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    first, _ = L.merge([], fresh()[:1])
    monkeypatch.setattr(L, "published", lambda url: {"entries": first, "started": "2026-10-21T00:00:00Z"})
    monkeypatch.setattr(L, "collect", lambda api, url: fresh())
    assert L.main(["--out", str(tmp_path)]) == 0
    got = json.loads((tmp_path / "answers.json").read_text())
    assert got["started"] == "2026-10-21T00:00:00Z" and got["entries"][0] == first[0] and len(got["entries"]) == 2
    assert got["head"] == got["entries"][-1]["hash"] and L.verify(got["entries"]) is None
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "check.js").read_text() == L.CHECK_JS.read_text()


def test_the_first_build_starts_a_chain(tmp_path, monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(L, "published", lambda url: [])
    monkeypatch.setattr(L, "collect", lambda api, url: [])
    assert L.main(["--out", str(tmp_path)]) == 0
    got = json.loads((tmp_path / "answers.json").read_text())
    assert got["entries"] == [] and got["head"] == L.START and got["started"] == got["generated_at"]


def test_a_reordered_chain_with_its_links_rewritten_still_breaks():
    entries, _ = L.merge([], fresh())
    swapped = [dict(entries[1], prev=L.START), dict(entries[0], prev=entries[1]["hash"])]
    assert L.verify(swapped) == 0
    edited = json.loads(json.dumps(entries))
    edited[1]["prev"] = "f" * 64                                     # the link field alone changed
    assert L.verify(edited) == 1


def test_new_notes_go_in_the_order_they_were_written():
    notes = [note(4, summary("- `b`: kept, named by @alice"), at="2026-10-02T00:00:00Z"),
             note(3, summary("- `a`: kept, named by @alice"), at="2026-10-01T00:00:00Z"),
             note(9, summary("- `c`: kept, named by @alice"), at="2026-10-01T00:00:00Z")]
    entries, _ = L.merge([], L.entries_from(1, notes, URL))
    assert [e["note"] for e in entries] == [3, 9, 4]


def test_the_page_counts_who_answered_and_shows_the_jobs_note():
    entries, _ = L.merge([], fresh())
    html = L.page({"entries": entries, "head": entries[-1]["hash"], "started": "s", "changed_after_recorded": [],
                   "note": "From our own <test> runs."})
    assert "Answered by @alice (1), @bob (1)." in html and "From our own &lt;test&gt; runs." in html
    more, _ = L.merge([], fresh() + L.entries_from(9, [note(13, summary("- `z`: kept, named by @bob"))], URL))
    assert "Answered by @bob (2), @alice (1)." in L.page({"entries": more, "head": "h", "started": "s", "changed_after_recorded": []})


def test_the_note_is_kept_out_of_the_chain(tmp_path, monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(L, "published", lambda url: [])
    monkeypatch.setattr(L, "collect", lambda api, url: fresh())
    assert L.main(["--out", str(tmp_path), "--note", "ours"]) == 0
    got = json.loads((tmp_path / "answers.json").read_text())
    assert got["note"] == "ours" and L.verify(got["entries"]) is None and all("note" not in e or isinstance(e["note"], int) for e in got["entries"])
    assert L.main(["--out", str(tmp_path), "--owners", "alice,bob"]) == 0
    assert json.loads((tmp_path / "answers.json").read_text())["owners"] == ["alice", "bob"]
    assert "From the project owner's accounts" in (tmp_path / "index.html").read_text()


def test_the_page_splits_the_owners_answers_from_outside_ones():
    entries, _ = L.merge([], fresh())
    base = {"entries": entries, "head": entries[-1]["hash"], "started": "s", "changed_after_recorded": []}
    html = L.page(dict(base, owners=["alice"]))
    assert "From the project owner's accounts: @alice (1). <strong>From outside the project: @bob (1).</strong>" in html
    assert "<td>@bob <strong>(outside the project)</strong></td>" in html and "<td>@alice</td>" in html
    assert "From outside" not in L.page(dict(base, owners=["alice", "bob"])) and "outside the project" not in L.page(base)
    assert "From the project owner" not in L.page(dict(base, owners=["zed"]))


def test_the_pages_job_owner_list_is_the_committed_one():
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parent.parent
    owners = re.search(r"--owners (\S+)", (root / ".gitlab-ci.yml").read_text()).group(1).split(",")
    assert owners == json.loads((root / "eval" / "outside_answer_rubric.json").read_text())["owner_accounts"]
