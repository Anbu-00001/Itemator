"""The custom review instructions for GitLab Duo's reviewers (.gitlab/duo/mr-review-instructions.yaml) keep the documented shape
(instructions: [{name, fileFilters, instructions}]) and point at the same kinds of change Itemator's rules list."""
import fnmatch
import pathlib

import yaml

FILE = pathlib.Path(__file__).resolve().parent.parent / ".gitlab" / "duo" / "mr-review-instructions.yaml"
EXAMPLES = {"Dependencies the issue did not ask for": ["pyproject.toml", "web/package.json", "svc/requirements-dev.txt"],
            "CI and configuration changes the issue did not ask for": [".gitlab-ci.yml", ".github/workflows/x.yml", "app/Dockerfile"],
            "Tests removed or weakened": ["tests/test_ci.py", "pkg/x_test.go", "app/spec/models/u_spec.rb"],
            "Files that instruct coding agents": ["AGENTS.md", "docs/AGENTS.md", ".github/copilot-instructions.md", "skills/a/SKILL.md"]}


def groups():
    return yaml.safe_load(FILE.read_text())["instructions"]


def test_every_group_has_the_documented_keys_and_nothing_else():
    assert [g["name"] for g in groups()] == list(EXAMPLES)
    for g in groups():
        assert set(g) == {"name", "fileFilters", "instructions"} and g["fileFilters"] and g["instructions"].strip()


def test_each_group_matches_its_example_files():
    for g in groups():
        for path in EXAMPLES[g["name"]]:
            assert any(fnmatch.fnmatch(path, f) for f in g["fileFilters"]), (g["name"], path)


def test_the_file_says_the_comments_are_advice_and_a_person_decides():
    assert "advice to the reviewer only" in FILE.read_text() and "decided by a person" in FILE.read_text()
