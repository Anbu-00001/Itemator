"""T26 B2 and F4: a thread offers `split` and `remove` only where the react flow accepts them (its Step 5a part 3),
and a grouped dependency thread lists every package it stands for, so the flow can tell a listed manifest line from
one the issue asked for. Real git repositories in tmp, a fake GitLab API, no network."""
import pytest

from itemator import ci
from itemator.extras import Extra
from test_ci import FIXED, FakeHttp, isolated, issue, job, mr, repo, routes  # noqa: F401  (fixtures)

KEEP = "To keep it, reply with its exact name; a line under the name can say why."
SPLIT = "To move it into its own MR, reply `split`."
REMOVE = "To drop it from this MR, reply `remove`."
TAIL = "If this is not really an extra, reply `not an extra`."
BOTH, REMOVE_ONLY, NEITHER = ("split", "remove"), ("remove",), ()


def added(path):
    return {path: {"filename": path, "status": "added"}}


def modified(path):
    return {path: {"filename": path, "status": "modified"}}


def check_stub(stub, name, offers):
    assert stub.split("`")[1] == ci.shown_name(name) and stub.count(KEEP) == 1 and stub.endswith(TAIL)
    assert (SPLIT in stub) is ("split" in offers) and (REMOVE in stub) is ("remove" in offers)
    at = [stub.index(s) for s in (KEEP, SPLIT, REMOVE, TAIL) if s in stub]
    assert at == sorted(at)


@pytest.mark.parametrize("e, by_path, offers", [
    (Extra("ci_or_config", ".gitlab-ci.yml", ".gitlab-ci.yml", "x"), modified(".gitlab-ci.yml"), BOTH),
    (Extra("ci_or_config", "deploy/Dockerfile", "deploy/Dockerfile", "x"), {}, BOTH),
    (Extra("ci_or_config", "conf/app.ini", "conf/app.ini", "x"), added("conf/app.ini"), BOTH),
    (Extra("ci_or_config", "package.json", "build", "x"), {}, NEITHER),               # an npm script: one line of a manifest
    (Extra("ci_or_config", "pyproject.toml", "pyproject.toml", "x"), {}, NEITHER),    # a manifest is not a config file here
    (Extra("ci_or_config", "Makefile", "Makefile", "x"), {}, NEITHER),
    (Extra("ci_or_config", "conf/", "conf/", "x", ("conf/a.yml", "conf/b.yml")), {}, NEITHER),
    (Extra("new_dependency", "requirements.txt", "colorama", "x"), {}, BOTH),
    (Extra("new_dependency", "api/requirements-dev.txt", "colorama", "x"), {}, BOTH),
    (Extra("new_dependency", "go.mod", "github.com/a/b", "x"), {}, BOTH),
    (Extra("new_dependency", "setup.py", "colorama", "x"), {}, NEITHER),
    (Extra("new_dependency", "requirements.txt", "requirements.txt", "x", ("a", "b")), {}, NEITHER),  # a list without its items
    (Extra("stray_file", "notes.txt", "notes.txt", "x"), added("notes.txt"), REMOVE_ONLY),
    (Extra("stray_file", "notes.txt", "notes.txt", "x"), modified("notes.txt"), NEITHER),
    (Extra("stray_file", "notes.txt", "notes.txt", "x"), {}, NEITHER),
    (Extra("stray_file", "./", "stray files", "x", ("a", "b")), added("./"), NEITHER),
    (Extra("binary_or_large_added", "assets/logo.png", "assets/logo.png", "x"), added("assets/logo.png"), REMOVE_ONLY),
    (Extra("build_output_added", "dist/app.js", "dist/app.js", "x"), added("dist/app.js"), REMOVE_ONLY),
    (Extra("build_output_added", "dist/", "dist/", "x", ("dist/a.js",)), {}, NEITHER),
    (Extra("tests_removed", "tests/test_a.py", "tests/test_a.py", "x"), added("tests/test_a.py"), NEITHER),
    (Extra("public_api_removed", "src/m.py", "parse", "x"), {}, NEITHER),
    (Extra("generated_code_removed", "gen/a.pb.go", "gen/a.pb.go", "x"), {}, NEITHER),
    (Extra("version_bump", "pyproject.toml", "1.1.0", "x"), {}, NEITHER),
    (Extra("policy_changed", ".itemator.toml", ".itemator.toml", "x"), added(".itemator.toml"), NEITHER),
])
def test_a_thread_offers_only_what_the_react_flow_accepts(e, by_path, offers):
    assert ci.answers(e, (), by_path) == offers
    check_stub(ci.describe_extra(e, by_path)["thread_stub"], e.name, offers)


def group(n, width):
    deps = [Extra("new_dependency", "requirements.txt", f"pkg{i}-" + "x" * width, f"adds pkg{i}") for i in range(n)]
    [(e, items)] = ci.group_extras(deps)
    return e, items


def test_a_grouped_dependency_thread_lists_every_package_and_offers_both():
    e, items = group(7, 3)
    assert e.name == e.path == "requirements.txt" and len(items) == 7
    stub = ci.describe_extra(e, {}, items)["thread_stub"]
    listed = stub.split("new dependencies in requirements.txt: ")[1].split(". ")[0].split(", ")
    assert listed == [i.name for i in items]
    check_stub(stub, "requirements.txt", BOTH)


def test_a_grouped_thread_too_long_to_list_offers_neither():
    e, items = group(6, 160)                    # 6 names of 165 characters and 5 separators: exactly MAX_LISTED
    assert len(", ".join(i.name for i in items)) == ci.MAX_LISTED and ci.answers(e, items, {}) == BOTH
    e, items = group(6, 161)
    assert ci.answers(e, items, {}) == NEITHER
    check_stub(ci.describe_extra(e, {}, items)["thread_stub"], "requirements.txt", NEITHER)


def test_the_in_scope_dependency_is_never_named_by_the_extra_thread(repo, tmp_path, monkeypatch):
    """The T24 case: the issue asks for requests-cache; colorama is the extra. The colorama thread names only
    colorama, so the react flow's part 3(b) refuses to split or remove a requirements.txt that also adds
    requests-cache (the prompt is read by the audit; this is the data it relies on)."""
    head = repo.commit({"src/parser.py": FIXED,
                        "requirements.txt": "requests==2.31.0\nrequests-cache==1.2.0\ncolorama==0.4.6\n"})
    code, out = job(repo, head, FakeHttp(routes(mr(), [issue(title="Fix the parser and add requests-cache")])),
                    tmp_path, monkeypatch)
    assert code == 0 and [(e["kind"], e["name"]) for e in out["extras"]] == [("new_dependency", "colorama")]
    stub = out["extras"][0]["thread_stub"]
    assert "requests-cache" not in stub and "requests_cache" not in stub
    check_stub(stub, "colorama", BOTH)


# ---- T37 item 3: an agent instruction file offers `remove` only when the merge request adds that one file; the react flow
# refuses whole-file and multi-file edits of existing files, so a modified, deleted or grouped one offers neither
@pytest.mark.parametrize("e, by_path, offers", [
    (Extra("agent_instructions", ".github/copilot-agent.yml", ".github/copilot-agent.yml", "w"),
     added(".github/copilot-agent.yml"), REMOVE_ONLY),
    (Extra("agent_instructions", ".github/copilot-instructions.md", ".github/copilot-instructions.md", "w"),
     modified(".github/copilot-instructions.md"), NEITHER),
    (Extra("agent_instructions", "AGENTS.md", "AGENTS.md", "w"), {"AGENTS.md": {"filename": "AGENTS.md", "status": "removed"}},
     NEITHER),
    (Extra("agent_instructions", "./", "agent instruction files", "w", ("AGENTS.md", "CLAUDE.md")),
     {**added("AGENTS.md"), **added("CLAUDE.md")}, NEITHER),
])
def test_agent_instructions_offer_remove_only_for_one_added_file(e, by_path, offers):
    assert ci.answers(e, (), by_path) == offers
    check_stub(ci.thread_stub(e, offers=ci.answers(e, (), by_path)), e.name, offers)
    assert ci._label(e).startswith("agent instructions")


# ---- T40: `always` keeps the extra and opens a merge request that adds its path to ignore.paths on the target branch.
# Offered only for one CI/config or stray file named by its path, a path fnmatch and TOML read literally, never a
# package manifest or a kind the policy cannot quiet, and only when the target branch's policy file was read and used.
import json                                                       # noqa: E402
import pathlib                                                    # noqa: E402
import re                                                         # noqa: E402

from itemator import policy as POL                                # noqa: E402
from itemator.extras import KINDS, Analysis                        # noqa: E402

ALWAYS = ("To keep it and stop asking about this file, reply `always`; that opens a merge request that changes the "
          "team policy.")
GOOD = {"source": "target_branch", "sha": "a" * 40, "file": ".itemator.toml", "found": True, "ignored": None, "paths_line_ok": True,
        "active": {"other_person_required": False, "ignore_kinds": [], "ignore_paths": [], "ignores_every_path": []}}


def policy_dict(**change):
    out = json.loads(json.dumps(GOOD))
    paths = change.pop("paths", None)
    if paths is not None:
        out["active"]["ignore_paths"] = paths
    return {**out, **change}


def offers_always(e, items=(), by_path=None, policy=GOOD):
    return "always" in ci.answers(e, items, by_path or {}, ci.always_allowed(policy))


def one_file(kind, path="conf/app.ini"):
    return Extra(kind, path, path, "x")


@pytest.mark.parametrize("kind", sorted(set(KINDS) | {"policy_changed"}))
def test_always_only_for_a_config_or_stray_file(kind):
    assert offers_always(one_file(kind), by_path=added("conf/app.ini")) is (kind in ("ci_or_config", "stray_file"))


@pytest.mark.parametrize("e, items", [
    (Extra("ci_or_config", "conf/", "conf/", "x", ("conf/a.yml", "conf/b.yml")), ()),          # grouped, by detail
    (Extra("stray_file", "a.txt", "a.txt", "x"), (Extra("stray_file", "a.txt", "a.txt", "x"),) * 2),   # grouped, by items
    (Extra("stray_file", "./", "stray files", "x", ("a", "b")), ()),                           # a group name
    (Extra("ci_or_config", "package.json", "build", "x"), ()),                                 # one line of a file
    (Extra("ci_or_config", "Makefile", "build", "x"), ()),                                     # one target of a file
    (Extra("ci_or_config", "pyproject.toml", "pyproject.toml", "x"), ()),                      # a manifest
    (Extra("stray_file", "web/package.json", "web/package.json", "x"), ()),
    (Extra("ci_or_config", "requirements-dev.txt", "requirements-dev.txt", "x"), ()),
])
def test_always_never_for_a_group_a_line_or_a_manifest(e, items):
    assert not offers_always(e, items)


@pytest.mark.parametrize("path, ok", [
    ("a/B.c_d@e+f-g.yml", True), (".gitlab-ci.yml", True), ("Dockerfile", True), ("x" * 120, True),
    ("x" * 121, False), ("", False), ("conf/*.yml", False), ("conf/a?.yml", False), ("conf/[ab].yml", False),
    ("conf/a].yml", False), ("conf/!a.yml", False), ("conf/{a}.yml", False), ("conf/a b.yml", False),
    ("conf/a`b.yml", False), ('conf/a".yml', False), ("conf/a\\b.yml", False), ("conf/a'b.yml", False),
    ("conf/a#b.yml", False), ("conf/a,b.yml", False), ("conf/a~.yml", False), ("conf/é.yml", False),
    ("conf/a\n.yml", False), ("conf/a.yml\n", False), ("conf/a\t.yml", False),
])
def test_always_needs_a_plain_short_path(path, ok):
    for kind in ("ci_or_config", "stray_file"):
        assert offers_always(one_file(kind, path)) is ok, (kind, path)


def test_always_never_for_a_kind_the_policy_cannot_quiet(monkeypatch):
    assert offers_always(one_file("stray_file"))
    monkeypatch.setattr(POL, "NEVER_IGNORED", (*POL.NEVER_IGNORED, "stray_file"))
    assert not offers_always(one_file("stray_file")) and offers_always(one_file("ci_or_config"))


@pytest.mark.parametrize("policy, ok", [
    (GOOD, True),
    (None, False),
    (policy_dict(found=False), False),                                        # no file on the target branch
    (policy_dict(ignored="it is not valid TOML (line 2, column 8)"), False),  # a file that was not used
    (policy_dict(found=False, ignored="it could not be read (git ls-tree failed)"), False),
    (policy_dict(source="merge_base"), False),                                # the target branch was not read
    (policy_dict(paths_line_ok=False), False),                                # valid TOML the flow cannot extend (T42)
    (policy_dict(paths=[f"p{i}" for i in range(19)]), True),                  # room for one more
    (policy_dict(paths=[f"p{i}" for i in range(20)]), False),                 # POL.MAX_PATTERNS already
])
def test_always_needs_a_used_policy_file_on_the_target_branch(policy, ok):
    assert ci.always_allowed(policy) is ok
    assert offers_always(one_file("ci_or_config"), policy=policy) is ok


def test_always_is_not_offered_unless_asked():
    e = one_file("ci_or_config")
    assert ci.answers(e, (), {}) == BOTH and ci.answers(e, (), {}, False) == BOTH
    assert ci.answers(e, (), {}, True) == ("split", "remove", "always")
    assert ci.answers(one_file("stray_file"), (), added("conf/app.ini"), True) == ("remove", "always")
    assert ci.answers(one_file("stray_file"), (), modified("conf/app.ini"), True) == ("always",)
    assert ci.answers(one_file("tests_removed"), (), {}, True) == NEITHER


def test_the_always_sentence_comes_after_split_and_remove_and_before_not_an_extra():
    from test_registry import banned
    for e, by_path, words in ((one_file("ci_or_config"), {}, (SPLIT, REMOVE)),
                              (one_file("stray_file"), added("conf/app.ini"), (REMOVE,)),
                              (one_file("stray_file"), modified("conf/app.ini"), ())):
        offers = ci.answers(e, (), by_path, True)
        for stub in (ci.thread_stub(e, None, False, offers),
                     ci.thread_stub(e, "PyPI: x.", True, offers, said="silent")):
            assert stub.count(ALWAYS) == 1 and stub.endswith(f"{ALWAYS} {TAIL}")
            order = [KEEP, *words, ALWAYS, TAIL]
            assert [stub.count(s) for s in order] == [1] * len(order)
            assert [stub.index(s) for s in order] == sorted(stub.index(s) for s in order)
            assert stub.split("`")[1] == e.name and "reply with its exact name" in stub
            assert not banned().search(stub)
        full = ci.thread_stub(e, "PyPI: x.", True, offers, said="silent")
        before = ["PyPI: x.", "The description does not mention this.", ci.OTHER_PERSON, KEEP]
        assert [full.index(s) for s in before] == sorted(full.index(s) for s in before)
    assert ALWAYS not in ci.thread_stub(one_file("ci_or_config"))
    assert ci.ALWAYS == ALWAYS


def run_facts(monkeypatch, extras, policy, files=()):
    a = Analysis(list(extras), unplaced=[])
    monkeypatch.setattr(ci.X, "analyse", lambda *_, **__: a)
    issues = [{"iid": 12, "ref": "#12", "title": "t", "description": "d", "author_id": 1}]
    import datetime
    return ci.facts(mr_iid=5, mr_title="t", mr_description="", mr_author_id=2, issues=issues,
                    issues_from="closes_issues", files=list(files), repo="o/r", base_sha="a" * 40, head_sha="b" * 40,
                    warnings=[], now=datetime.datetime(2026, 10, 12, tzinfo=datetime.timezone.utc), policy=policy)


def test_facts_offer_always_only_with_a_used_policy(monkeypatch):
    extras = [one_file("ci_or_config", ".gitlab-ci.yml"), one_file("stray_file", "notes.txt"),
              Extra("new_dependency", "requirements.txt", "leftpad", "adds leftpad"),
              one_file("binary_or_large_added", "logo.png")]
    files = [{"filename": "notes.txt", "status": "added"}, {"filename": "logo.png", "status": "added"}]
    sha = "c" * 40
    for policy, want in ((POL.Policy(sha=sha, found=True, paths_line_ok=True), [True, True, False, False]),
                             (POL.Policy(sha=sha, found=True), [False] * 4),
                         (POL.Policy(sha=sha), [False] * 4),
                         (POL.Policy(sha=sha, found=True, ignored="it is not UTF-8 text"), [False] * 4),
                         (POL.Policy(sha=sha, found=True, source="merge_base"), [False] * 4),
                         (None, [False] * 4)):
        out = run_facts(monkeypatch, extras, policy, files)
        assert [ALWAYS in x["thread_stub"] for x in out["extras"]] == want, policy


OWN = pathlib.Path(__file__).resolve().parent.parent / ".itemator.toml"
OWN_TEXT = OWN.read_text() if OWN.exists() else "[names]\nother_person_required = false\n[ignore]\nkinds = []\npaths = []\n"
OWN_TEXT = OWN_TEXT.replace("hold_until_named = true", "hold_until_named = false")     # a held job fails on purpose: not what this test is about


@pytest.mark.parametrize("policy, want", [(OWN_TEXT, True), ("[ignore]\npaths = 3\n", False), (None, False)])
def test_job_offers_always_with_the_repository_policy_file(repo, tmp_path, monkeypatch, policy, want):
    """End to end: the target branch carries this repository's own .itemator.toml (valid, nothing quieted), an
    invalid one, or none."""
    if policy is not None:
        repo.base = repo.commit({".itemator.toml": policy}, "target branch")
    head = repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": "test:\n  script: [pytest, ruff]\n"})
    code, out = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    assert code == 0 and [x["name"] for x in out["extras"]] == [".gitlab-ci.yml"], out["extras"]
    assert (ALWAYS in out["extras"][0]["thread_stub"]) is want


# ---- the replay records: with a used, empty policy, the facts are what they were without one, except the policy's
# own `found` and the stubs that gain the `always` sentence (re-derived here from the brief, not from ci.py)
ROOT = pathlib.Path(__file__).resolve().parent.parent
_MANIFEST_NAME = re.compile(r"pyproject\.toml|package\.json|requirements(?:-[^/]*)?\.txt|go\.mod|Cargo\.toml|Gemfile")


def brief_offers_always(x: dict) -> bool:
    path = x["path"]
    return (x["kind"] in ("ci_or_config", "stray_file") and x.get("raw_name", x["name"]) == path and not x["detail"]
            and "detail" not in x["plain_facts"] and bool(re.fullmatch(r"[A-Za-z0-9._/@+-]{1,120}", path))
            and not _MANIFEST_NAME.fullmatch(path.rsplit("/", 1)[-1]))


def test_replay_records_gain_the_always_sentence_only_where_offered(monkeypatch):
    from test_checker_job import cached_files
    paths = sorted((ROOT / "results").glob("replay_v4_*.json"))
    if not paths:
        pytest.skip("no results/ in this copy")
    cache, seen, gained, listed = cached_files(), 0, {}, []
    for path in paths:
        for rec in json.loads(path.read_text())["prs"]:
            v4 = rec.get("v4", rec)
            extras = [Extra(x["kind"], x["path"], x["name"], x["why"], tuple(x["detail"])) for x in v4["extras"]]
            files = cache.get(rec["files_sha256"], [])
            off = json.loads(json.dumps(run_facts(monkeypatch, extras, POL.Policy(sha="a" * 40), files)))
            on = json.loads(json.dumps(run_facts(monkeypatch, extras, POL.Policy(sha="a" * 40, found=True, paths_line_ok=True), files)))
            assert off["policy"]["found"] is False and on["policy"]["found"] is True
            assert {**on["policy"], "found": False, "paths_line_ok": False} == off["policy"]
            assert {k: v for k, v in on.items() if k not in ("extras", "policy")} == \
                {k: v for k, v in off.items() if k not in ("extras", "policy")}, rec["pr_url"]
            assert len(on["extras"]) == len(off["extras"])
            for x, y in zip(on["extras"], off["extras"]):
                assert {**x, "thread_stub": ""} == {**y, "thread_stub": ""}
                changed = x["thread_stub"] != y["thread_stub"]
                assert changed is brief_offers_always(x), (rec["pr_url"], x["kind"], x["path"])
                if changed:
                    assert x["thread_stub"] == y["thread_stub"].replace(f" {TAIL}", f" {ALWAYS} {TAIL}")
                    gained[x["kind"]] = gained.get(x["kind"], 0) + 1
                    listed.append(f"{rec['pr_url']} {x['kind']} {x['path']}")
            seen += 1
    assert seen == 240 and gained.get("ci_or_config") and gained.get("stray_file")
    print(f"{seen} replay records; stubs that gain the always sentence: {gained}")
    print("\n".join(listed))
