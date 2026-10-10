"""Hand-made fixtures: one positive per kind, plus negatives."""
from itemator.extras_v2 import extras, analyse   # v1-era fixtures, run on the frozen v2 rules; test_extras_v3.py re-runs them on v3


def f(filename, patch=None, status="modified", previous_filename=None):
    d = {"filename": filename, "status": status, "patch": patch}
    if previous_filename:
        d["previous_filename"] = previous_filename
    return d


def kinds(result):
    return sorted({(e.kind, e.name) for e in result})


ISSUE = "Login fails when the password has a space\n\nSee `src/auth/login.py`, function `check_password`."
INSIDE = f("src/auth/login.py", "@@ -10,2 +10,2 @@ def check_password(raw):\n-    return raw.strip() == stored\n+    return raw == stored\n")


# ---- new_dependency
def test_new_dependency_in_requirements():
    req = f("requirements.txt", "@@ -1,2 +1,3 @@\n requests==2.31.0\n+httpx==0.27.0\n flask==3.0\n")
    assert kinds(extras(ISSUE, [INSIDE, req])) == [("new_dependency", "httpx")]


def test_version_bump_is_not_a_new_dependency():
    req = f("requirements.txt", "@@ -1,2 +1,2 @@\n-requests==2.30.0\n+requests==2.31.0\n flask==3.0\n")
    assert extras(ISSUE, [INSIDE, req]) == []


def test_dependency_named_in_issue_is_not_extra():
    req = f("requirements.txt", "@@ -1 +1,2 @@\n flask==3.0\n+bcrypt>=4\n")
    assert extras(ISSUE + "\nUse bcrypt for the comparison.", [INSIDE, req]) == []


def test_npm_dependency_and_scripts():
    pkg = f("package.json", '@@ -5,6 +5,8 @@\n   "scripts": {\n-    "test": "jest"\n+    "test": "jest --ci",\n+    "lint": "eslint ."\n   },\n   "dependencies": {\n+    "left-pad": "^1.3.0",\n     "react": "^18.2.0"\n')
    assert kinds(extras(ISSUE, [INSIDE, pkg])) == [("new_dependency", "left-pad")]


def test_go_indirect_and_pyproject_keywords_are_not_dependencies():
    gomod = f("go.mod", "@@ -3,3 +3,5 @@ require (\n \tgithub.com/a/b v1.0.0\n+\tgithub.com/c/d v1.2.0 // indirect\n+\tgithub.com/spf13/cobra v1.8.0\n )\n")
    pyproj = f("pyproject.toml", '@@ -4,3 +4,4 @@\n keywords = [\n     "cli",\n+    "auth",\n ]\n'
                                 '@@ -30,3 +31,5 @@\n     "web",\n+    "oauth",\n+    "pyjwt>=2.8",\n     "click>=8",\n')
    assert kinds(extras(ISSUE, [INSIDE, gomod, pyproj])) == [("new_dependency", "github.com/spf13/cobra"),
                                                             ("new_dependency", "pyjwt")]


# ---- ci_or_config
def test_ci_config_change_is_extra():
    ci = f(".github/workflows/test.yml", "@@ -1 +1 @@\n-python-version: 3.11\n+python-version: 3.12\n")
    assert kinds(extras(ISSUE, [INSIDE, ci])) == [("ci_or_config", ".github/workflows/test.yml")]


def test_ci_config_mentioned_is_not_extra():
    ci = f(".github/workflows/test.yml", "@@ -1 +1 @@\n-a\n+b\n")
    assert extras(ISSUE + "\nAlso the CI job is flaky.", [INSIDE, ci]) == []


# ---- tests_removed
def test_deleted_test_file_is_extra():
    gone = f("tests/test_session.py", "@@ -1,3 +0,0 @@\n-def test_expiry():\n-    assert True\n", status="removed")
    assert kinds(extras(ISSUE, [INSIDE, gone])) == [("tests_removed", "tests/test_session.py")]


def test_net_removed_assertions_is_extra():
    t = f("tests/test_login.py", "@@ -1,4 +1,2 @@\n def test_login():\n-    assert login('a b')\n-    assert login('c')\n+    assert login('a b')\n")
    assert kinds(extras(ISSUE, [INSIDE, t])) == [("tests_removed", "tests/test_login.py")]


def test_tests_moved_between_files_are_not_removed():
    a = f("tests/test_login.py", "@@ -1,2 +1,0 @@\n-def test_space():\n-    assert login('a b')\n")
    b = f("tests/test_login_space.py", "@@ -0,0 +1,2 @@\n+def test_space():\n+    assert login('a b')\n", status="added")
    assert extras(ISSUE, [INSIDE, a, b]) == []


# ---- public_api_removed
def test_removed_public_function_is_extra():
    mod = f("src/auth/tokens.py", "@@ -1,4 +1,1 @@\n-def issue_token(user):\n-    return sign(user)\n-\n def _helper():\n")
    assert ("public_api_removed", "issue_token") in kinds(extras(ISSUE, [INSIDE, mod]))


def test_private_or_redefined_or_named_symbols_are_not_extras():
    mod = f("src/auth/login.py", "@@ -1,6 +1,4 @@\n-def _strip(raw):\n-    return raw\n-def check_password(raw):\n+def check_password(raw, stored):\n-def hash_value(x):\n+def hash_value(x, salt):\n-export function legacy() {}\n")
    assert extras(ISSUE, [mod]) == []


def test_removed_js_export_is_extra():
    js = f("src/auth/api.ts", "@@ -1,3 +1,1 @@\n-export const refreshToken = () => {}\n-export { a, b as logoutAll }\n+const a = 1\n")
    found = kinds(extras(ISSUE, [INSIDE, js]))
    assert ("public_api_removed", "refreshToken") in found and ("public_api_removed", "logoutAll") in found


# ---- file_outside_ask
def test_file_outside_ask():
    files = [INSIDE,
             f("src/auth/session.py", "@@ -1 +1 @@\n-a\n+b\n"),          # same directory as a named file
             f("tests/test_login.py", "@@ -1 +1,2 @@\n x\n+y\n"),        # test of a named file
             f("src/billing/invoice.py", "@@ -1 +1 @@\n-a\n+b\n"),       # outside
             f("README.md", "@@ -1 +1 @@\n-a\n+b\n"),                   # docs: never alone
             f("package-lock.json", "@@ -1 +1 @@\n-a\n+b\n")]           # lockfile: never alone
    assert kinds(extras(ISSUE, files)) == [("file_outside_ask", "src/billing/invoice.py")]


def test_prose_issue_names_files_through_words():
    issue = "Add a dark mode toggle to the settings page"
    files = [f("web/components/DarkModeToggle.tsx", "@@ -0,0 +1 @@\n+x\n", status="added"),
             f("web/theme/palette.ts", "@@ -1 +1 @@\n-a\n+b\n")]
    assert kinds(extras(issue, files)) == [("file_outside_ask", "web/theme/palette.ts")]


def test_generic_directory_names_do_not_anchor():
    issue = "The api client should retry on 503"
    files = [f("src/net/retry.py", "@@ -1 +1 @@\n-a\n+b\n"),
             f("src/api/unrelated.py", "@@ -1 +1 @@\n-a\n+b\n")]   # "api" is generic: no anchor
    assert kinds(extras(issue, files)) == [("file_outside_ask", "src/api/unrelated.py")]


def test_no_anchor_abstains():
    a = analyse("Something is broken, please fix", [f("x/y/z.py", "@@ -1 +1 @@\n-a\n+b\n")])
    assert a.extras == [] and a.anchored is False


# ---- negatives and determinism
def test_change_inside_the_ask_has_no_extras():
    t = f("tests/test_login.py", "@@ -1 +1,3 @@\n x\n+def test_space():\n+    assert check_password('a b')\n")
    assert extras(ISSUE, [INSIDE, t]) == []


def test_deterministic_order():
    files = [f("src/billing/invoice.py", "@@ -1 +1 @@\n-def charge():\n+x\n"),
             f("requirements.txt", "@@ -0,0 +1 @@\n+httpx\n", status="added"),
             INSIDE]
    first = [e.to_dict() for e in extras(ISSUE, files)]
    assert first == [e.to_dict() for e in extras(ISSUE, list(reversed(files)))]
    assert [e["kind"] for e in first] == ["new_dependency", "public_api_removed", "file_outside_ask"]


def test_test_file_of_a_named_file_is_inside():
    issue = "Checkout total is wrong in the summary"
    files = [f("src/ui/summary.py", "@@ -1 +1 @@\n-a\n+b\n"),           # named by its stem
             f("src/checkout/cart.py", "@@ -1 +1 @@\n-a\n+b\n"),        # rule 5c: named by its directory
             f("tests/unit/test_cart.py", "@@ -1 +1 @@\n-a\n+b\n")]     # rule 5d: test of cart.py
    assert extras(issue, files) == []
