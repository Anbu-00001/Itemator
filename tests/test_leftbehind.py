"""itemator/leftbehind.py: a change moves PHP (or any runtime or image) in one file; the card names every other file that
still pins the old version. Real git repositories in tmp, a fake GitLab API, no network."""
import pytest

from itemator import leftbehind as L
from test_ci import FakeHttp, isolated, issue, job, mr, repo, routes  # noqa: F401  (fixtures)

CVE_ISSUE = issue(title="PHP2Shell: update PHP for CVE-2026-109618",
                  description="PHP 8.3.36 and 8.2.35 fix CVE-2026-109618. Update the Dockerfile.")
BASE = {
    "Dockerfile": "FROM php:8.3.35-fpm\nRUN docker-php-ext-install pdo\n",
    ".gitlab-ci.yml": "test:\n  image: php:8.3.30-cli\n  script: [phpunit]\nlegacy:\n  image: php:8.2.20-cli\n  script: [phpunit]\n",
    "deploy/compose.staging.yml": "services:\n  web:\n    image: php:8.3.35-fpm\n  cache:\n    image: redis:7.2.4\n",
    ".php-version": "8.3.35\n",
    "deploy/compose.dev.yml": "services:\n  web:\n    image: php:8.3-fpm\n",
    "docs/install.md": "Run php:8.3.30-cli\n",
}


def facts(repo, files, tmp_path, monkeypatch, the_issue=CVE_ISSUE):
    repo.base = repo.commit(BASE, "base")
    head = repo.commit(files)
    code, out = job(repo, head, FakeHttp(routes(mr(), [the_issue])), tmp_path, monkeypatch)
    assert code == 0
    return out


def by_name(out):
    return {e["name"]: e for e in out["extras"]}


def test_the_copies_left_on_the_old_line_each_get_a_thread_on_the_moved_line(repo, tmp_path, monkeypatch):
    out = facts(repo, {"Dockerfile": "FROM php:8.3.36-fpm\nRUN docker-php-ext-install pdo\n"}, tmp_path, monkeypatch)
    got = by_name(out)
    assert set(got) == {".gitlab-ci.yml", "deploy/compose.staging.yml", ".php-version"}
    assert out["state"] == "extras"
    ci_e = got[".gitlab-ci.yml"]
    assert ci_e["kind"] == "left_behind" and ci_e["anchor"] == {"old_path": "Dockerfile", "new_path": "Dockerfile", "old_line": None, "new_line": 1}
    assert ci_e["why"].startswith("still pins php 8.3.30 (image, line 2), 8.2.20 (image, line 5), while this change moves php to 8.3.36 in Dockerfile")
    staging = got["deploy/compose.staging.yml"]["thread_stub"]
    assert "To move it to the new version too, reply `bump`: in `deploy/compose.staging.yml`, `image: php:8.3.35-fpm` becomes `image: php:8.3.36-fpm`." in staging
    assert "reply `split`" not in staging and "reply `remove`" not in staging
    assert got[".php-version"]["thread_stub"].count("`8.3.35` becomes `8.3.36`") == 1
    assert out["card"]["final_line"].startswith("3 files beyond #12 still on the version this change moves away from: ")
    assert '"bump"' in out["card"]["todo_line"]
    rep = out["left_behind"]
    assert rep["moved"] == [{"path": "Dockerfile", "line": 1, "family": "php", "to": "8.3.36"}]
    assert rep["floating"] == [{"path": "deploy/compose.dev.yml", "line": 3, "tag": "8.3"}]


def test_with_the_cve_the_other_release_line_is_measured_against_its_listed_fix(repo, tmp_path, monkeypatch):
    out = facts(repo, {"Dockerfile": "FROM php:8.3.36-fpm\nRUN docker-php-ext-install pdo\n"}, tmp_path, monkeypatch)
    ci_e = by_name(out)[".gitlab-ci.yml"]
    assert "8.2.20 (image, line 5)" in ci_e["why"]              # one thread per file names both copies
    assert [c["to"] for c in ci_e["plain_facts"]["copies"]] == ["8.3.36", "8.2.35"]
    assert "reply `bump`" not in ci_e["thread_stub"]              # two copies in one file: no one-line edit


def test_without_a_cve_another_release_line_is_left_alone(repo, tmp_path, monkeypatch):
    plain = issue(title="Update PHP", description="Move the Dockerfile to PHP 8.3.36; 8.2.35 came out the same day.")
    out = facts(repo, {"Dockerfile": "FROM php:8.3.36-fpm\nRUN docker-php-ext-install pdo\n"}, tmp_path, monkeypatch, plain)
    ci_e = by_name(out)[".gitlab-ci.yml"]
    assert [c["version"] for c in ci_e["plain_facts"]["copies"]] == ["8.3.30"]
    assert "becomes `image: php:8.3.36-cli`" in ci_e["thread_stub"]


def test_a_change_that_moves_every_copy_on_its_line_leaves_only_the_other_line_the_issue_lists(repo, tmp_path, monkeypatch):
    out = facts(repo, {"Dockerfile": "FROM php:8.3.36-fpm\nRUN docker-php-ext-install pdo\n",
                       ".gitlab-ci.yml": BASE[".gitlab-ci.yml"].replace("8.3.30", "8.3.36"),
                       "deploy/compose.staging.yml": BASE["deploy/compose.staging.yml"].replace("8.3.35", "8.3.36"),
                       ".php-version": "8.3.36\n"}, tmp_path, monkeypatch)
    left = [e for e in out["extras"] if e["kind"] == "left_behind"]
    assert [(e["name"], [c["version"] for c in e["plain_facts"]["copies"]]) for e in left] == [(".gitlab-ci.yml", ["8.2.20"])]
    plain = issue(title="Update PHP", description="Move PHP to 8.3.36 everywhere.")
    out = facts(repo, {"Dockerfile": "FROM php:8.3.36-fpm\nRUN docker-php-ext-install pdo\n",
                       ".gitlab-ci.yml": BASE[".gitlab-ci.yml"].replace("8.3.30", "8.3.36"),
                       "deploy/compose.staging.yml": BASE["deploy/compose.staging.yml"].replace("8.3.35", "8.3.36"),
                       ".php-version": "8.3.36\n"}, tmp_path, monkeypatch, plain)
    assert not [e for e in out["extras"] if e["kind"] == "left_behind"]


def test_no_move_no_scan(repo, tmp_path, monkeypatch):
    out = facts(repo, {"src/a.py": "x = 1\n"}, tmp_path, monkeypatch)
    assert "left_behind" not in out and not [e for e in out["extras"] if e["kind"] == "left_behind"]


def test_a_downgrade_is_not_a_move(repo, tmp_path, monkeypatch):
    out = facts(repo, {"Dockerfile": "FROM php:8.3.20-fpm\nRUN docker-php-ext-install pdo\n"}, tmp_path, monkeypatch)
    assert not [e for e in out["extras"] if e["kind"] == "left_behind"]


def test_a_copy_marked_keep_is_not_asked_about(repo, tmp_path, monkeypatch):
    base = dict(BASE)
    base[".gitlab-ci.yml"] = "test:\n  # itemator: keep (we test the oldest supported PHP)\n  image: php:8.3.30-cli\n"
    repo.base = repo.commit(base, "base")
    head = repo.commit({"Dockerfile": "FROM php:8.3.36-fpm\nRUN docker-php-ext-install pdo\n"})
    code, out = job(repo, head, FakeHttp(routes(mr(), [CVE_ISSUE])), tmp_path, monkeypatch)
    assert ".gitlab-ci.yml" not in by_name(out)
    assert L.pins(".gitlab-ci.yml", "t:\n  image: php:8.3.30-cli  # itemator: keep\n") == []
    assert L.pins(".tool-versions", "php 8.3.30 # itemator: keep\n") == []


# ---- the parsers, one rule each

def pins(path, text):
    return [(p.family, p.shown, p.line, p.where) for p in L.pins(path, text)]


def test_dockerfile_pins():
    df = ("ARG PHP_VERSION=8.3.35\nFROM --platform=linux/amd64 php:${PHP_VERSION}-fpm-alpine3.20 AS base\nFROM base\n"
          "FROM scratch\nCOPY --from=composer:2.7.1 /usr/bin/composer /c\n# FROM php:8.1.0\nFROM node:${NODE}\nFROM ruby\n"
          "FROM php:8.5.12RC1-cli\nFROM docker.io/library/python:3.12.7@sha256:" + "a" * 64 + "\n")
    assert pins("Dockerfile", df) == [("php", "8.3.35", 1, "arg"), ("composer", "2.7.1", 5, "image"), ("python", "3.12.7", 10, "image")]
    assert L.pins("Dockerfile", df)[-1].digest is True


def test_ci_and_compose_pins():
    ci = ("default:\n  image:\n    name: php:8.3.30-cli\n    entrypoint: [\"\"]\nt:\n  services:\n    - mysql:8.0.36\n"
          "    - name: postgres:16.2\n      alias: db\n  parallel:\n    matrix:\n      - image: php:8.1.2\n  script:\n    - echo image: php:7.0.0\n"
          "u:\n  image: $CI_DEPENDENCY_PROXY_GROUP_IMAGE_PREFIX/php:8.3.29-cli\nv:\n  image: ${CUSTOM}/php:8.3.1\n")
    assert pins(".gitlab-ci.yml", ci) == [("php", "8.3.30", 3, "image"), ("mysql", "8.0.36", 7, "image"),
                                          ("postgres", "16.2", 8, "image"), ("php", "8.3.29", 16, "image")]
    co = "services:\n  app:\n    build: .\n    image: me/app:1.2.3\n  db:\n    image: ${DB:-postgres:16.1}\n  x:\n    image: ${DB}\n"
    assert pins("compose.yml", co) == [("postgres", "16.1", 6, "image")]


def test_workflow_and_version_file_pins():
    gh = ("jobs:\n  t:\n    container: node:20.11.1\n    steps:\n      - uses: shivammathur/setup-php@v2\n        with:\n"
          "          php-version: '8.3.30'\n      - uses: actions/setup-node@v4\n        with:\n          node-version: ${{ matrix.node }}\n"
          "      - with:\n          python-version: [\"3.11\", \"3.12\"]\n")
    assert pins(".github/workflows/t.yml", gh) == [("node", "20.11.1", 3, "image"), ("php", "8.3.30", 7, "setup-input")]
    assert pins(".tool-versions", "php 8.3.30 8.2.20\nnodejs 20.11.1 # pinned\n") == [
        ("php", "8.3.30", 1, "tool-versions"), ("php", "8.2.20", 1, "tool-versions"), ("node", "20.11.1", 2, "tool-versions")]
    assert pins(".nvmrc", "lts/*\n") == [] and pins(".nvmrc", "v20.11.1\n") == [("node", "v20.11.1", 1, "runtime-file")]
    assert pins(".python-version", "3.12\n") == [("python", "3.12", 1, "runtime-file")]


@pytest.mark.parametrize("path, skipped", [("vendor/x/Dockerfile", True), ("node_modules/a/compose.yml", True), ("docs/Dockerfile", True),
                                           ("README.md", True), ("deploy/Dockerfile", False), ("Dockerfile.prod", False)])
def test_where_the_scan_does_not_look(path, skipped):
    assert L.skipped_path(path) is skipped


@pytest.mark.parametrize("tag, want", [("8.3.36-fpm", ((8, 3, 36), "8.3.36", "-fpm")), ("v20.11.1", ((20, 11, 1), "v20.11.1", "")),
                                       ("8.5.12RC1-cli", None), ("latest", None), ("3.13b1", None), ("16", ((16,), "16", "")),
                                       ("8.3.4", ((8, 3, 4), "8.3.4", ""))])
def test_versions_read_as_numbers_and_never_a_release_candidate(tag, want):
    assert L.parse_version(tag) == want


def test_the_judge():
    m = L.Moved("Dockerfile", 1, "php", (8, 3, 35), (8, 3, 36), "8.3.36")
    pin = lambda v, s="x": L.Pin("a", 1, "x", "php", v, s, 0)
    assert L.judge(pin((8, 3, 30)), m, set()) == ("left", "8.3.36")
    assert L.judge(pin((8, 3, 4)), m, set()) == ("left", "8.3.36")            # numbers, not text: 8.3.4 < 8.3.36
    assert L.judge(pin((8, 3, 36)), m, set()) is None and L.judge(pin((8, 3, 40)), m, set()) is None
    assert L.judge(pin((8, 3)), m, set()) == ("floating", None) and L.judge(pin((8, 2)), m, set()) is None
    assert L.judge(pin((8, 2, 20)), m, set()) is None
    assert L.judge(pin((8, 2, 20)), m, {"8.2.35", "8.3.36"}) == ("left", "8.2.35")
    assert L.judge(pin((8, 2, 35)), m, {"8.2.35"}) is None
    major = L.Moved("x", 1, "node", (18,), (20,), "20")
    assert L.judge(L.Pin("a", 1, "x", "node", (18,), "18", 0), major, set()) == ("left", "20")


def test_the_one_line_edit_is_offered_only_when_it_is_safe():
    p = L.Pin("a", 2, "  image: php:8.3.30-cli", "php", (8, 3, 30), "8.3.30", 13)
    assert L.bump_line(p, "8.3.36") == ("image: php:8.3.30-cli", "image: php:8.3.36-cli")
    assert L.bump_line(L.Pin("a", 2, "image: php:8.3.30", "php", (8, 3, 30), "8.3.30", 11, digest=True), "8.3.36") is None
    assert L.bump_line(L.Pin("a", 2, "image: php:8.3.30", "php", (8, 3, 30), "8.3.30", 11, unique=False), "8.3.36") is None
    assert L.bump_line(L.Pin("a", 2, "image: php:8.3", "php", (8, 3), "8.3", 11), "8.3.36") is None
    assert L.bump_line(L.Pin("a", 2, "x: `php:8.3.30`", "php", (8, 3, 30), "8.3.30", 8), "8.3.36") is None


def test_a_path_the_policy_quiets_still_gets_its_old_copy_named_a_kind_entry_quiets_it(repo, tmp_path, monkeypatch):
    plain = issue(title="Update PHP", description="Move the Dockerfile to PHP 8.3.36.")
    for policy, want in (('[ignore]\npaths = [".gitlab-ci.yml"]\n', True), ('[ignore]\nkinds = ["left_behind"]\n', False)):
        base = dict(BASE, **{".itemator.toml": policy})
        repo.base = repo.commit(base, "base")
        head = repo.commit({"Dockerfile": "FROM php:8.3.36-fpm\nRUN docker-php-ext-install pdo\n"})
        code, out = job(repo, head, FakeHttp(routes(mr(), [plain])), tmp_path, monkeypatch)
        assert (".gitlab-ci.yml" in by_name(out)) is want, policy


def test_a_name_another_extra_has_gets_the_runtime_added(repo, tmp_path, monkeypatch):
    plain = issue(title="Update PHP", description="Move the Dockerfile to PHP 8.3.36.")
    out = facts(repo, {"Dockerfile": "FROM php:8.3.36-fpm\nRUN docker-php-ext-install pdo\n",
                       ".gitlab-ci.yml": BASE[".gitlab-ci.yml"] + "lint:\n  script: [ruff]\n"}, tmp_path, monkeypatch, plain)
    names = {e["name"]: e["kind"] for e in out["extras"]}
    assert names.get(".gitlab-ci.yml (old php)") == "left_behind" and names.get(".gitlab-ci.yml") == "ci_or_config"
    stub = by_name(out)[".gitlab-ci.yml (old php)"]["thread_stub"]
    assert "reply `split`" not in stub and "reply `remove`" not in stub and "reply `bump`" in stub    # the file is in the diff
    assert out["card"]["final_line"] == ("1 thing beyond #12: `.gitlab-ci.yml` (CI change); 3 files beyond #12 still on the version this change "
                                         "moves away from: `.gitlab-ci.yml (old php)`, `.php-version`, `deploy/compose.staging.yml`.")


PLAIN = issue(title="Update PHP", description="Move the Dockerfile to PHP 8.3.36.")
MOVED_DOCKERFILE = {"Dockerfile": "FROM php:8.3.36-fpm\nRUN docker-php-ext-install pdo\n"}


def test_a_copy_moved_along_by_one_line_is_the_same_fix_not_a_new_extra(repo, tmp_path, monkeypatch):
    """What `bump` writes: the next pipeline must not ask about the copy it just moved."""
    out = facts(repo, MOVED_DOCKERFILE | {".gitlab-ci.yml": BASE[".gitlab-ci.yml"].replace("8.3.30", "8.3.36")},
                tmp_path, monkeypatch, PLAIN)
    assert ".gitlab-ci.yml" not in by_name(out)
    assert out["left_behind"]["followed"] == [".gitlab-ci.yml"]
    assert set(by_name(out)) == {".php-version", "deploy/compose.staging.yml"}


@pytest.mark.parametrize("ci", [
    BASE[".gitlab-ci.yml"].replace("8.3.30", "8.3.36").replace("[phpunit]", "[phpunit, deploy]", 1),   # more than the pin
    BASE[".gitlab-ci.yml"].replace("8.3.30-cli", "8.3.36-cli\n  tags: [x]"),                       # a line added too
    BASE[".gitlab-ci.yml"].replace("8.3.30", "8.3.37"),                                            # another version
    BASE[".gitlab-ci.yml"].replace("php:8.3.30-cli", "php:8.3.36-zts"),                            # the flavour changed
])
def test_a_copy_moved_with_anything_else_is_still_asked_about(repo, tmp_path, monkeypatch, ci):
    out = facts(repo, MOVED_DOCKERFILE | {".gitlab-ci.yml": ci}, tmp_path, monkeypatch, PLAIN)
    assert by_name(out)[".gitlab-ci.yml"]["kind"] == "ci_or_config"
    assert out["left_behind"]["followed"] == []


def test_a_move_only_extras_make_is_no_ask_to_follow(repo, tmp_path, monkeypatch):
    docs = issue(title="Fix the README typo", description="The README says 'teh'.")
    out = facts(repo, {"README.md": "the\n", ".gitlab-ci.yml": BASE[".gitlab-ci.yml"].replace("8.3.30", "8.3.36")},
                tmp_path, monkeypatch, docs)
    assert by_name(out)[".gitlab-ci.yml"]["kind"] == "ci_or_config"


def test_single_reads_the_whole_file():
    before = "test:\n  image: php:8.3.30-cli\n"
    files = [{"filename": ".gitlab-ci.yml", "status": "modified"}]
    m = [L.Moved(".gitlab-ci.yml", 2, "php", (8, 3, 30), (8, 3, 36), "8.3.36")]
    assert L.single(files, m, lambda p: before, lambda p: before.replace("30", "36")) == {".gitlab-ci.yml": m[0]}
    assert L.single(files, m, lambda p: before, lambda p: before.replace("30", "36") + "x: 1\n") == {}
    assert L.single(files, m, lambda p: before, lambda p: None) == {}
    assert L.single(files, m + m, lambda p: before, lambda p: before.replace("30", "36")) == {}
