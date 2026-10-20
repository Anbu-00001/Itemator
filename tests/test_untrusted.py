"""itemator/untrusted.py: text a stranger writes, handed to something that runs or obeys it."""
import pytest

from itemator import checked as C
from itemator import ci
from itemator import untrusted as UT


def f(path, *added, status="modified", start=10):
    body = "".join(f"+{a}\n" for a in added)
    return {"filename": path, "status": status, "patch": f"@@ -{start},0 +{start},{len(added)} @@\n{body}"}


def kinds(*files):
    return [(d["kind"], d["line"]) for d in UT.find(list(files))]


@pytest.mark.parametrize("line", [
    '  - eval "echo $CI_MERGE_REQUEST_TITLE"',
    '  - bash -c "deploy $CI_COMMIT_REF_NAME"',
    '  - sh -c "echo ${CI_COMMIT_MESSAGE}"',
    '  - python3 -c "print(\'$CI_MERGE_REQUEST_DESCRIPTION\')"',
    '  - node -e "console.log(\\"$CI_COMMIT_TITLE\\")"',
    "  - jq \".title == \\\"$CI_MERGE_REQUEST_TITLE\\\"\" in.json",
    '  - sed -i "s/@@/$CI_MERGE_REQUEST_SOURCE_BRANCH_NAME/" a.txt',
    '  - awk "/$CI_COMMIT_BRANCH/" log',
    "  - eval $CI_MERGE_REQUEST_TITLE",
    "  script: eval $CI_COMMIT_MESSAGE",
])
def test_a_variable_handed_to_an_interpreter_is_named(line):
    assert kinds(f(".gitlab-ci.yml", line)) == [("interpreter", 10)]


@pytest.mark.parametrize("line", [
    '  - claude -p "Review this: $CI_MERGE_REQUEST_TITLE"',
    '  - gemini --prompt "$CI_MERGE_REQUEST_DESCRIPTION"',
    '  - codex exec "fix $CI_COMMIT_MESSAGE"',
    "  - aider --message \"$CI_COMMIT_TITLE\"",
])
def test_a_variable_in_an_agent_prompt_is_named(line):
    assert kinds(f(".gitlab-ci.yml", line)) == [("agent-prompt", 10)]


@pytest.mark.parametrize("line", [
    '  - echo "$CI_MERGE_REQUEST_TITLE"',
    "  - git checkout $CI_COMMIT_REF_NAME",
    "  - curl -d \"t=$CI_MERGE_REQUEST_TITLE\" https://x.example",
    "  - eval 'echo $CI_MERGE_REQUEST_TITLE'",
    '  - eval "echo $CI_COMMIT_REF_SLUG"',
    '  - eval "echo $CI_COMMIT_SHA"',
    '  - eval "echo $CI_COMMIT_BRANCH_EXTRA"',
    "  - eval $OTHER",
    '  rules:',
    '    - if: $CI_COMMIT_BRANCH == "main"',
    '  variables:',
    '    TITLE: $CI_MERGE_REQUEST_TITLE',
    '    CMD: eval $CI_MERGE_REQUEST_TITLE',
    '  # - eval $CI_MERGE_REQUEST_TITLE',
    '  - echo claude is a model, $CI_COMMIT_SHA',
])
def test_a_quoted_or_unrelated_use_is_not(line):
    assert kinds(f(".gitlab-ci.yml", line)) == []


def test_a_github_expression_in_a_script_line_is_named():
    nx = ["      - name: Validate PR title",
          '        run: |',
          '          echo "${{ github.event.pull_request.title }}" | grep -E "^(feat|fix)"']
    assert kinds(f(".github/workflows/pr-title-validation.yml", *nx)) == [("github-expression", 12)]
    assert kinds(f(".github/workflows/a.yml", "        run: git pull origin ${{ github.head_ref || github.ref }}")) == [("github-expression", 10)]
    assert kinds(f(".github/workflows/a.yml", "          echo ${{ github.event.head_commit.message }} > m.txt")) == [("github-expression", 10)]


def test_a_github_expression_in_a_mapping_is_the_safe_pattern():
    assert kinds(f(".github/workflows/a.yml", "        env:", "          TITLE: ${{ github.event.pull_request.title }}", "        with:", "          title: ${{ github.event.pull_request.title }}")) == []
    assert kinds(f(".github/workflows/a.yml", "        run: echo ${{ github.sha }} ${{ github.event.pull_request.number }}")) == []


def test_shell_scripts_are_read_but_other_files_are_not():
    line = 'eval "$CI_MERGE_REQUEST_TITLE"'
    assert kinds(f("ci/check.sh", line)) == [("interpreter", 10)]
    assert kinds(f("tools/run.sh", line)) == [("interpreter", 10)]
    assert kinds(f("src/app.py", 'eval("$CI_MERGE_REQUEST_TITLE")'), f("README.md", "  - eval $CI_MERGE_REQUEST_TITLE"), f("tests/test_a.sh", line),
                 f("docs/ci.yml", "  - eval $CI_MERGE_REQUEST_TITLE")) == []


def test_removed_and_patchless_files_are_not_read():
    assert kinds(f(".gitlab-ci.yml", "  - eval $CI_COMMIT_MESSAGE", status="removed"), {"filename": ".gitlab-ci.yml", "status": "modified"}) == []


def test_the_list_is_capped_and_the_sentence_names_three():
    found = UT.find([f(".gitlab-ci.yml", *[f"  - eval $CI_COMMIT_MESSAGE {i}" for i in range(UT.MAX_FOUND + 4)])])
    assert len(found) == UT.MAX_FOUND
    s = UT.sentence(found)
    assert s.count("hands text a stranger writes to an interpreter") == 3 and s.endswith(f"and {UT.MAX_FOUND - 3} more.")


def test_each_kind_has_its_own_words():
    s = UT.sentence([{"path": "a.yml", "line": 1, "kind": k, "text": ""} for k in ("github-expression", "interpreter", "agent-prompt")])
    assert "before the shell runs it" in s and "an interpreter that runs it" in s and "AI tool's prompt" in s


def test_the_card_carries_the_line_before_the_shapes_line():
    u = UT.find([f(".gitlab-ci.yml", '  - claude -p "$CI_MERGE_REQUEST_TITLE"')])
    sh = [{"path": "s.sh", "line": 1, "kind": "env-to-network", "text": ""}]
    s = C.sentence([], [], [], [], None, [], [], None, [], None, None, sh, u)
    assert s.startswith("Also checked, with no model: The change adds lines that treat a title") and s.index("treat a title") < s.index("supply-chain")


def test_also_checked_reports_untrusted_text_and_never_changes_the_state(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    report = {"extras": [], "warnings": [], "card": {}, "state": "clean"}
    ci.also_checked(report, str(tmp_path), "b" * 40, "h" * 40, [f(".gitlab-ci.yml", "  - eval $CI_COMMIT_MESSAGE")], None, None)
    assert report["checked"]["untrusted"] == [{"path": ".gitlab-ci.yml", "line": 10, "kind": "interpreter", "text": "- eval $CI_COMMIT_MESSAGE"}]
    assert "treat a title" in report["card"]["checked_line"] and report["state"] == "clean"


def test_an_agent_prompt_outranks_an_interpreter_on_the_same_line():
    assert kinds(f(".gitlab-ci.yml", '  - claude -p "$CI_MERGE_REQUEST_TITLE" | jq .')) == [("agent-prompt", 10)]


def test_every_line_of_a_shell_script_is_a_command():
    assert kinds(f("ci/check.sh", "title: eval $CI_MERGE_REQUEST_TITLE")) == [("interpreter", 10)]
    assert kinds(f(".gitlab-ci.yml", "    title: eval $CI_MERGE_REQUEST_TITLE")) == []


def test_shown_text_is_cut():
    assert len(UT.find([f(".gitlab-ci.yml", "  - eval $CI_COMMIT_MESSAGE " + "x" * 200)])[0]["text"]) == 80


def test_a_stranger_term_anywhere_in_the_expression_is_named():
    first = '          ISSUE_TITLE="${{ github.event.issue.title || github.event.pull_request.title }}"'
    last = "        run: x=${{ inputs.branch || github.event.pull_request.head.ref }}"
    assert kinds(f(".github/workflows/a.yml", first, last)) == [("github-expression", 10), ("github-expression", 11)]
    assert kinds(f(".github/workflows/a.yml", "        run: echo ${{ inputs.branch || github.sha }} ${{ github.event.pull_request.number }}")) == []


def test_composite_action_files_are_read_like_workflows_and_other_yaml_is_not():
    line = '        run: echo "${{ github.event.issue.title }}"'
    assert kinds(f("action.yml", line)) == [("github-expression", 10)]
    assert kinds(f(".github/actions/setup/action.yaml", line)) == [("github-expression", 10)]
    assert kinds(f("src/my-action.yml", line), f("docs/action.yml.md", line), f("config.yml", line)) == []
    assert kinds(f("action.yml", "      env:", "        TITLE: ${{ github.event.issue.title }}")) == []


def test_every_expression_of_a_line_is_read_and_text_between_expressions_is_not():
    assert kinds(f(".github/workflows/a.yml", "        run: echo ${{ github.sha }} ${{ github.event.issue.title }}")) == [("github-expression", 10)]
    assert kinds(f(".github/workflows/a.yml", "        run: echo ${{ github.sha }} github.event.issue.title ${{ github.run_id }}")) == []


def test_an_escaped_quote_opens_no_string_and_a_quote_inside_double_quotes_is_a_character():
    assert UT._in_single_quotes("echo \\'x", 7) is False                  # \' is a literal quote: x is expanded
    assert UT._in_single_quotes("echo 'x", 6) is True
    assert UT._in_single_quotes('echo "it\'s" x', 12) is False
