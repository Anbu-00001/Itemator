"""Rules v6 (T37): one failing-then-passing fixture per change, from T36's audit of agent-instruction-file hits and its
audit of sample E (sections 4 and 9).

The older fixtures run on their own frozen rules (test_extras_v5.py on extras_v5, and so on). Here every v1 to v5
fixture runs again on v6, through test_extras_v5's own runners with v6 in place of v5. A fixture whose expected output
v6 changes on purpose is in _CHANGED with the reason.
"""
import hashlib
import pathlib

import pytest

import test_extras_v3 as T3
import test_extras_v4 as T4
import test_extras_v5 as T5
from itemator import extras as V6
from itemator import extras_v3, extras_v4, extras_v5
from itemator.extras import analyse, extras

V5_SHA256 = "67f62f09fefc36f21cbf32bb4fcf895f5557dd0f7845b1d9a73a066062900682"   # extras.py of rules v5 (d40bbb6; sample E's rules_sha256)
EDIT, f, kinds, new = T3.EDIT, T3.f, T3.kinds, T4.new


# ---- the old fixtures, on v6
_CHANGED = {   # fixture id -> why v6 gives another answer; its v6 output is asserted below
    "test_extras_v2.test_r5_flags_only_files_away_from_every_named_file":
        "its modified .github/copilot-instructions.md is now an agent_instructions extra, not an unplaced name",
}
_NOT_FIXTURES = {"test_v1_v2_fixtures_hold_on_v5", "test_v3_fixtures_hold_on_v5", "test_v4_fixtures_hold_on_v5",
                 "test_versions_and_frozen_v4"}
OLD5 = [n for n in sorted(vars(T5)) if n.startswith("test_") and n not in _NOT_FIXTURES
        and f"test_extras_v5.{n}" not in _CHANGED]


def _on_v6(monkeypatch):
    for attr, value in (("V5", V6), ("analyse", V6.analyse), ("extras", V6.extras)):
        monkeypatch.setattr(T5, attr, value)


OLD12 = [(m, n) for m, n in T5.OLD12 if f"{m.__name__}.{n}" not in _CHANGED]
OLD3 = [n for n in T5.OLD3 if f"test_extras_v3.{n}" not in _CHANGED]
OLD4 = [n for n in T5.OLD4 if f"test_extras_v4.{n}" not in _CHANGED]


@pytest.mark.parametrize("mod,name", OLD12, ids=[f"{m.__name__}.{n}" for m, n in OLD12])
def test_v1_v2_fixtures_hold_on_v6(mod, name, monkeypatch):
    _on_v6(monkeypatch)
    T5.test_v1_v2_fixtures_hold_on_v5(mod, name, monkeypatch)


@pytest.mark.parametrize("name", OLD3)
def test_v3_fixtures_hold_on_v6(name, monkeypatch):
    _on_v6(monkeypatch)
    T5.test_v3_fixtures_hold_on_v5(name, monkeypatch)


@pytest.mark.parametrize("name", OLD4)
def test_v4_fixtures_hold_on_v6(name, monkeypatch):
    _on_v6(monkeypatch)
    T5.test_v4_fixtures_hold_on_v5(name, monkeypatch)


@pytest.mark.parametrize("name", OLD5)
def test_v5_fixtures_hold_on_v6(name, monkeypatch):
    _on_v6(monkeypatch)
    getattr(T5, name)()


def test_the_changed_v2_fixture_on_v6():
    issue = "Add a CLI command to invite people off the waitlist"
    files = [f("packages/backend/src/waitlist/waitlist.service.ts", EDIT),
             f("packages/backend/src/common/constants/env.constants.ts", EDIT), f("packages/backend/.env.example", EDIT),
             f("packages/core/src/mappers/map.ts", EDIT), f("global.json", EDIT), f(".github/copilot-instructions.md", EDIT)]
    a = analyse(issue, files)
    assert kinds(a.extras) == [("agent_instructions", ".github/copilot-instructions.md")]
    assert a.unplaced == ["global.json", "packages/core/src/mappers/map.ts"]


def test_versions_and_frozen_v5():
    assert V6.RULES_VERSION == 6 and V6.KINDS == extras_v5.KINDS + ("agent_instructions",)
    assert hashlib.sha256(pathlib.Path(extras_v5.__file__).read_bytes()).hexdigest() == V5_SHA256
    issue, files = "The waitlist invite fails", [f("waitlist.py", EDIT), f("deploy/k8s.yaml", EDIT)]
    assert type(analyse(issue, files, version=5)) is extras_v5.Analysis
    assert type(analyse(issue, files, version=4)) is extras_v4.Analysis
    assert type(analyse(issue, files, version=3)) is extras_v3.Analysis
    assert kinds(analyse(issue, files, version=2).extras) == [("file_outside_ask", "deploy/k8s.yaml")]
    assert kinds(analyse(issue, files, version=1).extras) == [("file_outside_ask", "deploy/k8s.yaml")]
    with pytest.raises(ValueError):
        analyse(issue, files, version=7)


# ---- change 1: agent_instructions (T36 audit of instruction-file hits; fixtures in the shape of its table)
CODE = f("packages/core/src/image.ts", EDIT)
RULER = "<!-- Source: .ruler/instructions.md -->\nWork on the dev branch.\nRun vitest before you commit."
MCP = '{"mcpServers": {"genaiscript": {"command": "node", "args": ["cli/dist/src/index.js", "mcp"]}}}'
TOLD = "changes what coding agents are told"


def test_agent_instruction_files_are_one_extra_and_leave_the_stray_group():      # genaiscript#1740 shape
    agents = [new("AGENTS.md", RULER), new("CLAUDE.md", RULER), new("GEMINI.md", RULER), new(".mcp.json", MCP),
              new(".cursor/mcp.json", MCP), new(".cursor/rules/ruler_cursor_instructions.mdc", RULER)]
    files = [CODE, *agents, new("NOTES.md", "scratch notes")]
    issue = "Allow to attach images for modifications in generateImage"
    old = extras_v5.analyse(issue, files)
    assert [e.kind for e in old.extras] == ["stray_file"] and len(old.extras[0].detail) == 5     # v5: a stray group of 5
    a = analyse(issue, files)
    assert kinds(a.extras) == [("agent_instructions", "agent instruction files"), ("stray_file", "NOTES.md")]
    (e,) = [x for x in a.extras if x.kind == "agent_instructions"]
    assert e.path == "./" and e.detail == tuple(sorted(x["filename"] for x in agents))
    assert e.why == (f"{TOLD}: 6 agent instruction files the issue does not ask for (6 added): .cursor/mcp.json, "
                     ".cursor/rules/ruler_cursor_instructions.mdc, .mcp.json, ...")
    assert a.stray == ["NOTES.md"] and not set(e.detail) & set(a.unplaced + a.named_paths)


@pytest.mark.parametrize("status, verb", [("modified", "edits"), ("removed", "deletes")])
def test_one_changed_instruction_file_is_named_by_its_path(status, verb):     # PSRule#2973, typespec#7439, a deletion
    md = f(".github/copilot-instructions.md", "@@ -10,2 +10,3 @@\n - Use pnpm.\n+- Always add a trailing newline.\n", status)
    files = [f("src/PSRule/Pipeline/AzurePipelinesAdapter.cs", EDIT), md]
    issue = "[FEATURE] Add adapter to support Azure Pipelines for v3\nAdd tooling support for Azure Pipelines to the CLI."
    assert extras_v5.extras(issue, files) == []                       # v5: an unplaced name at most
    a = analyse(issue, files)
    assert [(e.kind, e.path, e.name, e.detail) for e in a.extras] == [
        ("agent_instructions", md["filename"], md["filename"], ())]
    assert a.extras[0].why == f"{TOLD}: {verb} an agent instruction file the issue does not ask for"
    assert md["filename"] not in a.unplaced


def test_an_added_agent_permission_file_and_a_rename_are_extras():              # aztfmod#332 (Copilot firewall allow-list)
    yml = new(".github/copilot-agent.yml", "firewall:\n  allow:\n    - checkpoint-api.hashicorp.com")
    issue = "Combine resourceDefinition_out_of_docs.json and resourceDefinition.json with official documentation mapping"
    assert kinds(extras(issue, [f("resourceDefinition.json", EDIT), yml])) == [("agent_instructions", ".github/copilot-agent.yml")]
    moved = f("docs/agents-old.md", None, "renamed", previous_filename="AGENTS.md")
    assert kinds(extras(issue, [f("resourceDefinition.json", EDIT), moved])) == [("agent_instructions", "docs/agents-old.md")]
    assert "renames an agent instruction file" in extras(issue, [f("resourceDefinition.json", EDIT), moved])[0].why


@pytest.mark.parametrize("issue", [
    "Analyze repo and create copilot files\nCreate a `.github/copilot-instructions.md` file of under 250 words.",  # figma#3359
    "Extract copilot instructions from https://github.com/dotnet/maui/pull/30300",                                 # maui#30304
    "Add a note to the copilot-instructions file that this command should be used to format the codebase",         # maui#30230
    "Update the agent instructions with the new build command",
    "Add cursor rules for the test runner",
])
def test_an_issue_that_asks_for_agent_instructions_keeps_them_quiet(issue):        # the three "expected" cases stay quiet
    md = f(".github/copilot-instructions.md", "@@ -1,2 +1,3 @@\n # Rules\n+Run dotnet format before committing.\n")
    assert extras(issue, [md]) == []


def test_a_phrase_names_every_instruction_file_and_a_name_only_its_own():
    md = f(".github/copilot-instructions.md", "@@ -1,2 +1,3 @@\n # Rules\n+Run dotnet format before committing.\n")
    claude = new("CLAUDE.md", RULER)
    assert extras("Update the agent instructions with the new build command", [md, claude]) == []
    assert kinds(extras("Write a CLAUDE.md with the build commands", [md, claude])) == [
        ("agent_instructions", ".github/copilot-instructions.md")]
    rev = new(".github/agents/reviewer.yml", "name: reviewer")
    assert kinds(extras("See https://github.com/acme/app/blob/main/.github/agents/reviewer.yml", [rev, claude])) == [
        ("agent_instructions", "CLAUDE.md")]                    # a link names its file (through the base name), not the others
    assert kinds(extras("Fix the docs under packages/core", [new("packages/core/AGENTS.md", RULER)])) == [
        ("agent_instructions", "packages/core/AGENTS.md")]      # an ancestor directory does not name the file


def test_a_named_instruction_file_anchors_and_is_never_unplaced():
    md = f("AGENTS.md", "@@ -1,2 +1,3 @@\n # Agents\n+Run make test.\n")
    a = analyse("Update AGENTS.md with the test command", [md, f("src/runner/main.py", EDIT)])
    assert a.anchored and a.named_paths == ["AGENTS.md"] and a.extras == [] and a.unplaced == ["src/runner/main.py"]
    b = analyse("switch embedding model not works; the server always uses the default model",       # mcp-documentation-server#2
                [f(".github/copilot-instructions.md", "@@ -1,37 +1,118 @@\n-old\n+# AI Coding Agent guide\n"),
                 f("src/embeddings/provider.ts", EDIT)])
    assert kinds(b.extras) == [("agent_instructions", ".github/copilot-instructions.md")]
    assert ".github/copilot-instructions.md" not in b.unplaced


def test_mcp_names_the_mcp_settings_only():
    files = [CODE, new(".mcp.json", MCP), new(".cursor/mcp.json", MCP), new("AGENTS.md", RULER)]
    assert kinds(extras("Expose the CLI as an MCP server", files)) == [("agent_instructions", "AGENTS.md")]
    assert kinds(extras("Expose the CLI as a tool server", files)) == [("agent_instructions", "agent instruction files")]
    two = extras("Speed up the parser", [new(".claude/commands/a.md", "x"), new(".claude/settings.json", "{}")])
    assert [(e.path, e.name) for e in two] == [(".claude/", "agent instruction files")]   # named by the shared directory


@pytest.mark.parametrize("path, hit", [
    ("AGENTS.md", True), ("packages/core/CLAUDE.md", True), ("GEMINI.md", True), (".cursorrules", True),
    (".windsurfrules", True), (".mcp.json", True), ("tools/mcp.json", True), (".github/copilot-instructions.md", True),
    (".github/instructions/tests.instructions.md", True), (".github/agents/reviewer.yml", True),
    (".github/copilot-agent.yml", True), (".cursor/rules/style.mdc", True), (".cursor/mcp.json", True),
    (".gitlab/duo/agent-config.yml", True), (".gitlab/duo/mr-review-instructions.yaml", True),
    (".agents/rules/deep/x.md", True), ("skills/release/SKILL.md", True), ("tools/skills/lint/SKILL.md", True),
    (".claude/commands/review.md", True), (".codex/config.toml", True), (".copilot/mcp-config.json", True),
    (".github/workflows/copilot-setup-steps.yml", False), (".github/workflows/copilot-setup-steps.yml.yml", False),
    ("src/agents/AGENTS.py", False), ("skills/SKILL.md", False), (".github/instructions/sub/x.md", False),
    ("docs/mcp.json.md", False), ("README.md", False), ("claude/x.md", False),
])
def test_which_files_tell_agents_what_to_do(path, hit):
    assert V6.is_agent_instructions(path) is hit


def test_agent_files_leave_the_other_rules():          # here rule 10: two whitespace-only files are not a group of three
    ws = "@@ -1,2 +1,2 @@\n if x:\n-  return 1\n+    return 1\n"
    md = f(".github/copilot-instructions.md", "@@ -1,2 +1,2 @@\n # Rules\n-  - Use pnpm.\n+- Use pnpm.\n")
    assert kinds(extras("Speed up the parser", [f("src/a.py", ws), f("src/b.py", ws), md])) == [
        ("agent_instructions", ".github/copilot-instructions.md")]


def test_copilot_setup_steps_stays_a_ci_change():
    wf = new(".github/workflows/copilot-setup-steps.yml", "name: setup\non: workflow_dispatch")
    assert kinds(extras("Speed up the parser", [f("src/parser.py", EDIT), wf])) == [
        ("ci_or_config", ".github/workflows/copilot-setup-steps.yml")]


# ---- change 4 was measured and left out (T37 report): .NET build files are not config files (RulesEngine#674 shape)
def test_known_limit_dotnet_build_files_are_not_config():
    sdk = f("global.json", '@@ -1,5 +1,5 @@\n {\n   "sdk": {\n-    "version": "9.0.0",\n+    "version": "8.0.115",\n')
    proj = f("src/RulesEngine/RulesEngine.csproj", "@@ -1,3 +1,3 @@\n <PropertyGroup>\n"
             "-  <TargetFrameworks>net6.0;net8.0;net9.0</TargetFrameworks>\n+  <TargetFrameworks>net6.0;net8.0</TargetFrameworks>\n")
    issue = "5.0.3 to 5.0.6: Method 'SomeMethod' on type 'SomeType' is not accessible."
    assert extras(issue, [f("src/RulesEngine/RuleCompiler.cs", EDIT), sdk, proj]) == []      # the clear miss stays a miss
    assert V6._config_kind("global.json") is None and V6._config_kind("src/A/A.csproj") is None


# ---- change 5: a lower version says so (T36 audit of sample E, 9.2)
def _pj(old, new_):
    return f("package.json", f'@@ -1,3 +1,3 @@\n {{\n-  "version": "{old}",\n+  "version": "{new_}",\n')


@pytest.mark.parametrize("old, new_, lower", [
    ("9.0.0", "8.0.115", True), ("1.10.0", "1.9.0", True), ("2.0", "1.9.9", True),
    ("1.2.0", "1.10.0", False),                     # numbers, not text: 10 > 2
    ("1.2", "1.2.0", False), ("1.2.0", "1.2", False),   # the same version written longer or shorter
    ("2.0.0-beta", "1.0.0", False), ("2", "1", False),   # not both dotted numbers
    ("1.0.0", "1.1.0", False),
])
def test_a_lower_version_says_so(old, new_, lower):
    (e,) = extras("Fix the parser", [_pj(old, new_)])
    verb = "lowers the version" if lower else "changes the package version"
    assert e.why == f"{verb} from {old} to {new_}; the issue names neither version"
