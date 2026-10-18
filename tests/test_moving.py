"""itemator/moving.py: references a change adds that can change under it (latest images, branch includes, curl | sh)."""
import pytest

from itemator import checked as C
from itemator import ci
from itemator import moving as MV


def f(path, *added, status="modified", context=("script:",)):
    body = "".join(f" {c}\n" for c in context) + "".join(f"+{a}\n" for a in added)
    return {"filename": path, "status": status, "patch": f"@@ -1,{len(context)} +1,{len(context) + len(added)} @@\n{body}"}


def kinds(*files):
    return [(d["kind"], d["text"]) for d in MV.find(list(files))]


@pytest.mark.parametrize("line,expected", [
    ("image: node:latest", ("image-latest", "node:latest")),
    ("  image: registry.example.com:5000/team/app:latest", ("image-latest", "registry.example.com:5000/team/app:latest")),
    ("  - image: python", ("image-untagged", "python")),
    ('image: "ruby"', ("image-untagged", "ruby")),
    ("  ref: main", ("include-branch", "main")),
    ("    ref: 'HEAD'  # follows the default branch", ("include-branch", "HEAD")),
    ("  - remote: https://gitlab.com/g/p/-/raw/main/ci/x.yml", ("remote-branch", "https://gitlab.com/g/p/-/raw/main/ci/x.yml")),
    ("  - component: gitlab.com/g/p/build@~latest", ("component-branch", "gitlab.com/g/p/build@~latest")),
    ("  - component: gitlab.com/g/p/build@main", ("component-branch", "gitlab.com/g/p/build@main")),
    ("  - curl -fsSL https://x.sh/install | sudo bash", ("pipe-to-shell", "- curl -fsSL https://x.sh/install | sudo bash")),
])
def test_a_moving_reference_is_named(line, expected):
    assert kinds(f(".gitlab-ci.yml", line)) == [expected]


@pytest.mark.parametrize("line", [
    "image: node:20-alpine", "image: python:3.12", f"image: node@sha256:{'a' * 64}", "image: $CI_REGISTRY_IMAGE", "image: scratch",
    "  ref: 0123456789abcdef0123456789abcdef01234567", "  ref: v1.2.0", "  ref: main-fix-docs",
    "  - remote: https://gitlab.com/g/p/-/raw/0123456789abcdef/ci/x.yml", "  - component: gitlab.com/g/p/build@1.2.0",
    "# image: node:latest", "  - curl -fsSL https://x.sh/install -o install.sh", "  - curl -s https://x | tee out.txt",
])
def test_a_pinned_or_unrelated_line_is_not(line):
    assert kinds(f(".gitlab-ci.yml", line)) == []


def test_only_added_lines_are_read():
    removed = {"filename": ".gitlab-ci.yml", "status": "modified", "patch": "@@ -1,2 +1,1 @@\n-image: node:latest\n image: node:20\n"}
    context = f(".gitlab-ci.yml", context=("image: node:latest",))
    assert kinds(removed, context) == []


def test_text_outside_a_hunk_is_not_read():
    assert MV.added_lines("+image: node:latest\n@@ -1 +1 @@\n+ok\n") == ["ok"]


def test_dockerfiles_are_read_with_their_own_rule():
    assert kinds(f("Dockerfile", "FROM node:latest")) == [("image-latest", "node:latest")]
    assert kinds(f("docker/app.Dockerfile", "FROM --platform=linux/amd64 golang:latest AS build")) == [("image-latest", "golang:latest")]
    assert kinds(f("Dockerfile", "FROM builder")) == []                  # an untagged FROM is often a build stage
    assert kinds(f("Dockerfile", "RUN curl -sL https://x/setup | bash -")) == [("pipe-to-shell", "RUN curl -sL https://x/setup | bash -")]


def test_other_files_and_removed_files_are_not_read():
    assert kinds(f("README.md", "image: node:latest"), f("src/a.py", "x = 'curl a | sh'"), f(".gitlab-ci.yml", "image: node:latest", status="removed")) == []
    assert kinds({"filename": ".gitlab-ci.yml", "status": "modified"}) == []


def test_ci_files_in_subfolders_are_read():
    assert kinds(f("ci/build.yml", "image: node:latest")) == [("image-latest", "node:latest")]


def test_the_list_is_capped():
    assert len(MV.find([f(".gitlab-ci.yml", *[f"image: img{i}:latest" for i in range(MV.MAX_FOUND + 5)])])) == MV.MAX_FOUND


def test_the_sentence_names_three_and_counts_the_rest():
    found = MV.find([f(".gitlab-ci.yml", *[f"image: img{i}:latest" for i in range(5)], "  ref: main")])
    s = MV.sentence(found)
    assert s.count("an image tagged `latest`") == 3 and s.endswith("and 3 more.") and "`.gitlab-ci.yml`" in s
    assert "a download piped into a shell" in MV.sentence(MV.find([f(".gitlab-ci.yml", "  - wget -qO- https://x | sh")]))


def test_the_card_carries_the_moving_line_before_the_pipeline_line():
    found = MV.find([f(".gitlab-ci.yml", "image: node:latest")])
    s = C.sentence([], [], [], [], {"added": ["j"], "removed": [], "changed": [], "global": []}, [], [], None, found)
    assert s.startswith("Also checked, with no model: The change adds references") and s.index("references") < s.index("The project's pipeline")
    assert C.sentence([], [], [], [], None, [], [], None, []) is None


def test_also_checked_reports_moving_references_and_never_changes_the_state(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    report = {"extras": [], "warnings": [], "card": {}, "state": "clean"}
    ci.also_checked(report, str(tmp_path), "b" * 40, "h" * 40, [f(".gitlab-ci.yml", "image: node:latest")], None, None)
    assert report["checked"]["moving"] == [{"path": ".gitlab-ci.yml", "kind": "image-latest", "text": "node:latest"}]
    assert "can change under it" in report["card"]["checked_line"] and report["state"] == "clean"


def test_a_commented_download_is_not_a_reference():
    assert kinds(f(".gitlab-ci.yml", "  # - curl https://x | sh")) == []


def test_a_latest_tag_pinned_by_digest_is_pinned():
    assert kinds(f(".gitlab-ci.yml", f"image: node:latest@sha256:{'b' * 64}")) == []


def test_a_registry_port_is_not_a_tag():
    assert kinds(f(".gitlab-ci.yml", "image: registry.local:5000/team/app")) == [("image-untagged", "registry.local:5000/team/app")]


def test_include_lines_are_a_ci_file_thing():
    assert kinds(f("Dockerfile", "  ref: main", "  - component: x/y@main")) == []


def test_a_containerfile_is_read():
    assert kinds(f("Containerfile", "FROM alpine:latest")) == [("image-latest", "alpine:latest")]
