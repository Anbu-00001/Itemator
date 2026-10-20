"""Go modules added to go.mod: the proxy's version list and dates, the pinned version, names with capitals. A fake fetcher stands in for the network."""
import pytest

from itemator import registry as RG
from test_registry import Fake, OSV

PROXY = "https://proxy.golang.org/"


def routes(path="github.com/foo/bar", versions=("v1.0.0", "v1.2.0", "v2.0.0-rc.1"), dates=None, escaped=None):
    esc = escaped or path
    dates = dates or {"v1.0.0": "2019-04-01T10:00:00Z", "v1.2.0": "2024-02-03T10:00:00Z"}
    r = {f"{PROXY}{esc}/@v/list": (200, ("\n".join(versions) + "\n").encode()), OSV: (200, {"vulns": []})}
    for v, t in dates.items():
        r[f"{PROXY}{esc}/@v/{v}.info"] = (200, {"Version": v, "Time": t})
    return r


def look(fake, name="github.com/foo/bar", version=None):
    return RG.Run(fake, "2026-10-19").look({"ecosystem": "Go", "name": name, "version": version})


def test_facts_from_the_list_and_two_dates():
    fake = Fake(routes())
    rec = look(fake, version="v1.2.0")
    assert (rec["lookup"], rec["first_release"], rec["first_version"], rec["releases"], rec["latest"], rec["version_released"]) == \
           ("ok", "2019-04-01", "v1.0.0", 3, "v1.2.0", "2024-02-03")
    assert rec["license"] is None and rec["license_read"] is False and rec["advisories"] == 0
    assert [c["url"] for c in fake.calls][:3] == [PROXY + "github.com/foo/bar/@v/list", PROXY + "github.com/foo/bar/@v/v1.0.0.info",
                                                  PROXY + "github.com/foo/bar/@v/v1.2.0.info"]
    assert fake.calls[3]["body"] == {"package": {"name": "github.com/foo/bar", "ecosystem": "Go"}, "version": "v1.2.0"}


def test_the_sentence_does_not_say_no_licence_when_the_proxy_gives_none():
    assert "licence not given by its registry" in RG._facts(look(Fake(routes())))
    assert "no licence stated" not in RG._facts(look(Fake(routes())))


def test_capitals_are_escaped_the_way_the_proxy_wants():
    assert RG._go_escape("github.com/BurntSushi/toml") == "github.com/!burnt!sushi/toml"
    fake = Fake(routes("github.com/BurntSushi/toml", escaped="github.com/!burnt!sushi/toml"))
    rec = look(fake, "github.com/BurntSushi/toml")
    assert rec["lookup"] == "ok" and rec["found"] is True and fake.calls[0]["url"].endswith("!burnt!sushi/toml/@v/list")


def test_the_lowest_number_is_first_and_the_latest_is_stable():
    versions = ("v0.9.0", "v10.0.0", "v2.0.0", "v11.0.0-beta.1", "v1.0.0+incompatible")
    rec = look(Fake(routes(versions=versions, dates={"v0.9.0": "2015-05-05T00:00:00Z"})))
    assert (rec["first_version"], rec["latest"], rec["releases"]) == ("v0.9.0", "v10.0.0", 5)


def test_an_unknown_module_and_one_with_no_tagged_version():
    assert look(Fake({}))["found"] is False
    rec = look(Fake({f"{PROXY}github.com/foo/bar/@v/list": (200, b"\n")}))
    assert (rec["lookup"], rec["reason"]) == ("unavailable", "no_tagged_versions")


@pytest.mark.parametrize("name, ok", [("github.com/foo/bar", True), ("golang.org/x/net", True), ("example.com/a/../b", False),
                                       ("example.com//b", False), ("../x", False), ("a b/c", False), ("é.com/x", False), ("", False)])
def test_module_names_are_checked_before_any_request(name, ok):
    assert RG.valid_name("Go", name) is ok


def test_pinned_reads_the_require_line_only():
    assert RG.pinned("Go", "github.com/foo/bar", "\tgithub.com/foo/bar v1.2.3 // indirect") == "v1.2.3"
    assert RG.pinned("Go", "github.com/foo/bar", "require github.com/foo/bar v1.2.3+incompatible") == "v1.2.3+incompatible"
    assert RG.pinned("Go", "github.com/foo/bar", "\tgithub.com/foo/barx v1.2.3") is None
    assert RG.pinned("Go", "github.com/foo/bar", "\tgithub.com/foo/bar latest") is None
    assert RG.pinned("Go", "github.com/foo/bar", "\tgithub.com/foo/bar v1.2.3.4") is None
    assert RG.pinned("Go", "github.com/foo/bar", "\tngithub.com/foo/bar v1.2.3") is None


def test_a_date_that_cannot_be_read_leaves_the_first_release_out():
    rec = look(Fake(routes(dates={"v1.0.0": "not a date"})))
    assert rec["lookup"] == "ok" and rec["first_release"] is None


def test_the_proxy_is_the_only_new_host():
    assert RG.HOSTS == {"pypi.org", "registry.npmjs.org", "crates.io", "api.nuget.org", "proxy.golang.org", "api.osv.dev", "api.deps.dev"}
