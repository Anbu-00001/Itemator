"""itemator/ci.py flag_cleanup (T65): removed tests that name a feature flag whose definition the same change deletes."""
from itemator import ci
from itemator.extras import Extra

FLAG = {"filename": "config/feature_flags/gitlab_com_derisk/new_search.yml", "status": "removed", "patch": "-name: new_search"}
TEST = {"filename": "spec/features/search_spec.rb", "status": "modified",
        "patch": "@@ -1,9 +1,3 @@\n-  context 'with new_search disabled' do\n-    before { stub_feature_flags(new_search: false) }\n-    it 'works' do\n-    end\n-  end\n+  it 'x' do\n+  end"}
E = Extra("tests_removed", TEST["filename"], TEST["filename"], "removes 1 more test definitions than it adds")


def by(*files):
    return {f["filename"]: f for f in files}


def test_tests_removed_with_their_deleted_flag_get_the_fact():
    assert ci.flag_cleanup(E, by(FLAG, TEST)) == "new_search"
    stub = ci.thread_stub(E, flag="new_search")
    assert "The lines it removes name the feature flag `new_search`, whose definition this change deletes" in stub
    assert stub.index("whose definition") < stub.index(ci.KEEP)


def test_no_fact_without_a_deleted_definition_a_matching_name_or_the_kind():
    assert ci.flag_cleanup(E, by(TEST)) is None                                                   # no flag deleted
    assert ci.flag_cleanup(E, by(dict(FLAG, status="modified"), TEST)) is None                   # flag kept
    assert ci.flag_cleanup(E, by(dict(FLAG, filename="config/feature_flags/ops/other.yml"), TEST)) is None
    assert ci.flag_cleanup(E, by(dict(FLAG, filename="config/flags/new_search.yml"), TEST)) is None   # not a flag definition
    assert ci.flag_cleanup(Extra("ci_or_config", TEST["filename"], TEST["filename"], "x"), by(FLAG, TEST)) is None
    added = dict(TEST, patch="+  stub_feature_flags(new_search: false)\n-  it 'y' do")              # only an added line names it
    assert ci.flag_cleanup(E, by(FLAG, added)) is None
    longer = dict(TEST, patch="-  stub_feature_flags(new_search_v2: false)")                    # a longer name is not the flag
    assert ci.flag_cleanup(E, by(FLAG, longer)) is None
    header = dict(TEST, patch="--- a/new_search\n-  it 'y' do")                                  # a diff header is not a removed line
    assert ci.flag_cleanup(E, by(FLAG, header)) is None


def test_the_fact_reaches_the_thread_and_plain_facts():
    rec = ci.describe_extra(E, by(FLAG, TEST))
    assert rec["plain_facts"]["flag_cleanup"] == "new_search" and "feature flag `new_search`" in rec["thread_stub"]
    plain = ci.describe_extra(E, by(TEST))
    assert "flag_cleanup" not in plain["plain_facts"] and "feature flag" not in plain["thread_stub"]
