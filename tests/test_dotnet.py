"""NuGet packages added in .NET project files: what is read from a diff, the registry answer, and the card sentence.
A fake fetcher stands in for the network; the registry documents follow nuget.org's registration index."""
import datetime

from itemator import dotnet as DN
from test_registry import Fake, OSV

NOW = datetime.datetime(2026, 10, 19, 9, 0, tzinfo=datetime.timezone.utc)
BASE = "https://api.nuget.org/v3/registration5-semver1/"


def entry(version, published, lic="MIT", name="Acme.Widgets"):
    return {"catalogEntry": {"id": name, "version": version, "published": published, "licenseExpression": lic}}


def index(items_by_page, name="Acme.Widgets"):
    pages = [{"@id": f"{BASE}{name.lower()}/page/{i}.json", "count": len(items), "items": items}
             for i, items in enumerate(items_by_page)]
    return {"count": len(pages), "items": pages}


def patch(*lines):
    return "@@ -1,3 +1,4 @@\n" + "\n".join(lines)


def proj(path, *lines, status="modified"):
    return {"filename": path, "status": status, "patch": patch(*lines)}


REF = '+    <PackageReference Include="Acme.Widgets" Version="2.1.0" />'


def test_added_reference_is_found_with_its_exact_version():
    got = DN.find([proj("src/App.csproj", " <ItemGroup>", REF)])
    assert got == [{"path": "src/App.csproj", "name": "Acme.Widgets", "version": "2.1.0"}]


def test_a_version_range_or_property_is_not_a_pin():
    for v in ("[1.0,2.0)", "$(AcmeVersion)", "2.*", ""):
        got = DN.find([proj("a.csproj", f'+<PackageReference Include="X" Version="{v}" />')])
        assert got == [{"path": "a.csproj", "name": "X", "version": None}], v


def test_a_version_bump_is_not_a_new_package():
    files = [proj("a.csproj", '-<PackageReference Include="acme.widgets" Version="1.0.0" />', REF)]
    assert DN.find(files) == []


def test_central_and_config_forms_are_read():
    files = [proj("Directory.Packages.props", '+<PackageVersion Include="Serilog" Version="4.0.0" />'),
             proj("legacy/packages.config", '+  <package id="NUnit" version="3.14.0" targetFramework="net48" />')]
    assert [(p["name"], p["version"]) for p in DN.find(files)] == [("Serilog", "4.0.0"), ("NUnit", "3.14.0")]


def test_other_files_and_removed_files_are_ignored():
    files = [proj("README.md", REF), proj("a.csproj", REF, status="removed"), {"filename": "b.csproj", "status": "added"}]
    assert DN.find(files) == []


def test_the_same_package_twice_in_one_file_is_listed_once_and_the_list_is_capped():
    assert len(DN.find([proj("a.csproj", REF, REF)])) == 1
    many = [f'+<PackageReference Include="P{i}" Version="1.0.0" />' for i in range(DN.MAX_FOUND + 5)]
    assert len(DN.find([proj("a.csproj", *many)])) == DN.MAX_FOUND


def test_look_up_gives_the_registry_facts_and_asks_osv_with_the_registry_spelling():
    doc = index([[entry("1.0.0", "2021-03-01T10:00:00.000+00:00"), entry("2.1.0", "2026-10-10T10:00:00.000+00:00")]])
    fake = Fake({BASE + "acme.widgets/index.json": (200, doc), OSV: (200, {"vulns": []})})
    found = [{"path": "a.csproj", "name": "ACME.widgets", "version": "2.1.0"}]
    rec = DN.look_up(found, fake, NOW)[0]
    assert (rec["lookup"], rec["found"], rec["first_release"], rec["releases"], rec["license"], rec["latest"]) == \
           ("ok", True, "2021-03-01", 2, "MIT", "2.1.0")
    assert rec["version_released"] == "2026-10-10" and rec["advisories"] == 0
    assert fake.calls[0]["url"] == BASE + "acme.widgets/index.json"
    assert fake.calls[1]["body"]["package"] == {"name": "Acme.Widgets", "ecosystem": "NuGet"}
    assert fake.calls[1]["body"]["version"] == "2.1.0"


def test_a_package_with_pages_listed_by_link_has_its_first_and_last_page_fetched():
    full = index([[entry("1.0.0", "2012-05-01T10:00:00.000+00:00")], [entry("3.0.0", "2026-01-02T10:00:00.000+00:00", lic="Apache-2.0")]])
    bare = {"count": 2, "items": [{k: v for k, v in p.items() if k != "items"} for p in full["items"]]}
    pages = {p["@id"]: (200, p) for p in full["items"]}
    fake = Fake({BASE + "acme.widgets/index.json": (200, bare), OSV: (200, {"vulns": []}), **pages})
    rec = DN.look_up([{"path": "a.csproj", "name": "Acme.Widgets", "version": None}], fake, NOW)[0]
    assert (rec["first_release"], rec["releases"], rec["license"], rec["latest"]) == ("2012-05-01", 2, "Apache-2.0", "3.0.0")
    assert len(fake.calls) == 4


def test_a_page_link_to_another_place_is_not_followed():
    full = index([[entry("1.0.0", "2012-05-01T10:00:00.000+00:00")]])
    bare = {"count": 1, "items": [{"@id": "https://evil.example/page.json", "count": 1}]}
    fake = Fake({BASE + "acme.widgets/index.json": (200, bare)})
    rec = DN.look_up([{"path": "a.csproj", "name": "Acme.Widgets", "version": None}], fake, NOW)[0]
    assert rec["lookup"] == "unavailable" and rec["reason"] == "bad_response" and len(fake.calls) == 1
    assert full


def test_an_unknown_package_and_a_changed_name_and_a_bad_name():
    fake = Fake({BASE + "acme.other/index.json": (200, index([[entry("1.0.0", "2020-01-01T00:00:00.000+00:00")]]))})
    gone, other, bad = DN.look_up([{"name": "Nope.Pkg", "version": None}, {"name": "Acme.Other", "version": None},
                                   {"name": "../x", "version": None}], fake, NOW)
    assert gone["lookup"] == "ok" and gone["found"] is False
    assert other["lookup"] == "unavailable" and other["reason"] == "name_differs"
    assert bad["lookup"] == "unavailable" and bad["reason"] == "invalid_name"


def test_an_unlisted_release_date_of_1900_is_not_a_first_release():
    doc = index([[entry("1.0.0", "1900-01-01T00:00:00+00:00"), entry("1.1.0", "2022-02-02T00:00:00.000+00:00")]])
    fake = Fake({BASE + "acme.widgets/index.json": (200, doc), OSV: (200, {"vulns": []})})
    rec = DN.look_up([{"name": "Acme.Widgets", "version": None}], fake, NOW)[0]
    assert rec["first_release"] == "2022-02-02"


def test_the_latest_is_the_last_stable_release():
    doc = index([[entry("1.0.0", "2020-01-01T00:00:00.000+00:00"), entry("2.0.0", "2021-01-01T00:00:00.000+00:00"),
                  entry("3.0.0-beta1", "2026-09-01T00:00:00.000+00:00")]])
    fake = Fake({BASE + "acme.widgets/index.json": (200, doc), OSV: (200, {"vulns": []})})
    assert DN.look_up([{"name": "Acme.Widgets", "version": None}], fake, NOW)[0]["latest"] == "2.0.0"


def test_sentence_names_the_limit_and_the_facts():
    doc = index([[entry("1.0.0", "2021-03-01T10:00:00.000+00:00")]])
    fake = Fake({BASE + "acme.widgets/index.json": (200, doc), OSV: (200, {"vulns": []})})
    found = [{"path": "a.csproj", "name": "Acme.Widgets", "version": None}]
    line = DN.sentence(found, DN.look_up(found, fake, NOW))
    assert line.startswith("1 NuGet package added in .NET project files (the rules do not count these files as extras) (checked 2026-10-19): ")
    assert "`Acme.Widgets`: first released 2021-03-01, 1 release, licence MIT as declared by its publisher, 0 known advisories in any version" in line
    assert DN.sentence([], []) is None


def test_sentence_without_a_lookup_still_counts_the_packages():
    found = [{"path": "a.csproj", "name": "A", "version": None}, {"path": "a.csproj", "name": "B", "version": None}]
    assert DN.sentence(found, []) == "2 NuGet packages added in .NET project files (the rules do not count these files as extras)."


def test_only_three_packages_are_shown_and_the_rest_point_to_the_record():
    names = [f"P{i}" for i in range(5)]
    routes = {BASE + f"{n.lower()}/index.json": (200, index([[entry("1.0.0", "2020-01-01T00:00:00.000+00:00", name=n)]], name=n)) for n in names}
    fake = Fake({**routes, OSV: (200, {"vulns": []})})
    found = [{"path": "a.csproj", "name": n, "version": None} for n in names]
    line = DN.sentence(found, DN.look_up(found, fake, NOW))
    assert line.count("`P") == 3 and "2 more in `checked` in itemator.json" in line


def test_blank_lines_in_a_patch_are_skipped():
    got = DN.find([{"filename": "a.csproj", "status": "modified", "patch": "@@ -1 +1,3 @@\n\n" + REF + "\n\n"}])
    assert [p["name"] for p in got] == ["Acme.Widgets"]
