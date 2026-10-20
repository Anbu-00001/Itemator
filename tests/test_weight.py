"""What a new dependency brings along (itemator/weight.py): the deps.dev graph, the sizes, the card words. A fake fetcher stands in
for the network; the graph documents follow deps.dev's v3 GetDependencies answers read on 2026-10-19 (fleet 43 R1)."""
import datetime
import json

from itemator import registry as RG, weight as W
from test_registry import Fake, OSV, pypi_doc

NOW = datetime.datetime(2026, 10, 19, 9, 0, tzinfo=datetime.timezone.utc)
GRAPH = "https://api.deps.dev/v3/systems/pypi/packages/leftpad-py/versions/1.2.0:dependencies"


def node(name, version, relation="DIRECT", bundled=False):
    return {"versionKey": {"system": "PYPI", "name": name, "version": version}, "bundled": bundled, "relation": relation, "errors": []}


def wheel(name, version, size, tag="py3-none-any"):
    return {"filename": f"{name}-{version}-{tag}.whl", "size": size, "yanked": False}


def ver_doc(*files):
    return {"urls": list(files)}


def ask_from(fake):
    run = RG.Run(fake, "2026-10-19")
    return run._ask


def graph(*nodes):
    return {"nodes": list(nodes), "edges": [], "error": ""}


ROUTES = {
    GRAPH: (200, graph(node("leftpad-py", "1.2.0", "SELF"), node("tiny", "0.1"), node("big", "2.0", "INDIRECT"))),
    "https://pypi.org/pypi/leftpad-py/1.2.0/json": (200, ver_doc(wheel("leftpad_py", "1.2.0", 10_000))),
    "https://pypi.org/pypi/tiny/0.1/json": (200, ver_doc(wheel("tiny", "0.1", 2_000), {"filename": "tiny-0.1.tar.gz", "size": 1_000})),
    "https://pypi.org/pypi/big/2.0/json": (200, ver_doc(wheel("big", "2.0", 30_000_000, "cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64"),
                                                         wheel("big", "2.0", 9_000_000, "cp312-cp312-macosx_11_0_arm64"))),
}


def test_a_dependency_is_weighed_from_its_graph_and_each_package_size():
    w = W.weigh(ask_from(Fake(ROUTES)), "PyPI", "leftpad-py", "1.2.0")
    assert (w["weight"], w["packages"], w["direct"], w["sized"], w["of"], w["bytes"], w["capped"]) == ("ok", 3, 1, 3, 3, 30_012_000, False)
    assert [x["name"] for x in w["largest"]] == ["big", "leftpad-py"]
    assert W.part(w) == "with what it brings along, 3 packages (2 more than the line names) and about 30 MB to download on every fresh install"


def test_the_wheel_is_picked_in_pips_order_the_most_specific_tag_first():
    cp312 = wheel("x", "1", 500, "cp312-cp312-manylinux_2_17_x86_64")
    abi3 = wheel("x", "1", 400, "cp39-abi3-manylinux_2_17_x86_64")
    pylinux = wheel("x", "1", 70, "py3-none-manylinux2014_x86_64")
    pure, sdist = wheel("x", "1", 900), {"filename": "x-1.tar.gz", "size": 100}
    assert W.pick_wheel([pure, sdist, pylinux, abi3, cp312])["size"] == 500          # pip takes cp312 over a pure wheel
    assert W.pick_wheel([pure, sdist, pylinux, abi3])["size"] == 400
    assert W.pick_wheel([pure, sdist, pylinux])["size"] == 70
    assert W.pick_wheel([pure, sdist])["size"] == 900
    assert W.pick_wheel([sdist, wheel("x", "1", 7, "cp312-cp312-win_amd64")])["size"] == 100
    assert W.pick_wheel([wheel("x", "1", 7, "cp312-cp312-win_amd64")]) is None
    assert W.pick_wheel([pylinux, wheel("x", "1", 6, "py3-none-manylinux2014_aarch64")])["size"] == 70
    assert W.pick_wheel([{**pure, "yanked": True}, sdist])["size"] == 100


def test_bundled_packages_are_inside_another_and_not_counted():
    routes = dict(ROUTES)
    routes[GRAPH] = (200, graph(node("leftpad-py", "1.2.0", "SELF"), node("tiny", "0.1", bundled=True)))
    w = W.weigh(ask_from(Fake(routes)), "PyPI", "leftpad-py", "1.2.0")
    assert (w["packages"], w["bytes"]) == (1, 10_000)
    assert W.part(w) == "it brings no other package (about 10 kB to download on a fresh install)"


def test_an_unknown_size_is_counted_as_unknown_never_guessed():
    routes = dict(ROUTES)
    del routes["https://pypi.org/pypi/big/2.0/json"]
    w = W.weigh(ask_from(Fake(routes)), "PyPI", "leftpad-py", "1.2.0")
    assert (w["sized"], w["of"], w["bytes"]) == (2, 3, 12_000)
    assert W.part(w).endswith("and at least 12 kB to download on every fresh install (1 size not given)")


def test_a_large_graph_is_sized_up_to_the_cap_and_said_to_be_at_least(monkeypatch):
    monkeypatch.setattr(W, "MAX_NODES", 2)
    w = W.weigh(ask_from(Fake(ROUTES)), "PyPI", "leftpad-py", "1.2.0")
    assert (w["packages"], w["of"], w["capped"], w["bytes"]) == (3, 2, True, 12_000)
    assert W.part(w).startswith("with what it brings along, at least 3 packages") and "at least 12 kB" in W.part(w)


def test_no_graph_an_error_graph_and_unsupported_ecosystems_say_nothing():
    assert W.weigh(ask_from(Fake({})), "PyPI", "leftpad-py", "1.2.0") == {"weight": "unavailable", "reason": "graph_http_404"}
    err = Fake({GRAPH: (200, {"nodes": [], "error": "could not resolve"})})
    assert W.weigh(ask_from(err), "PyPI", "leftpad-py", "1.2.0") == {"weight": "unavailable", "reason": "graph_error"}
    assert W.weigh(ask_from(Fake({GRAPH: (200, graph())})), "PyPI", "leftpad-py", "1.2.0")["reason"] == "empty_graph"
    for eco in ("crates.io", "Go", "NuGet", "RubyGems"):
        assert W.weigh(ask_from(Fake({})), eco, "x", "1.0")["weight"] == "not_supported"
    assert W.weigh(ask_from(Fake({})), "PyPI", "x", None)["weight"] == "no_version"
    assert W.part(None) is None and W.part({"weight": "unavailable"}) is None


def test_npm_names_and_sizes_use_the_tarball_length():
    assert W.size_request("npm", "@types/node", "20.11.0") == ("SIZE", "https://registry.npmjs.org/@types/node/-/node-20.11.0.tgz")
    assert W.size_request("npm", "express", "4.21.0") == ("SIZE", "https://registry.npmjs.org/express/-/express-4.21.0.tgz")
    assert W.graph_url("npm", "@types/node", "20.11.0") == "https://api.deps.dev/v3/systems/npm/packages/%40types%2Fnode/versions/20.11.0:dependencies"
    assert W.read_size("npm", 206, b"57884") == 57884 and W.read_size("npm", 404, b"1") is None and W.read_size("npm", 206, b"") is None


def test_sizes():
    assert [W.human(n) for n in (1, 499, 999_499, 1_000_000, 9_949_999, 10_400_000)] == ["1 kB", "1 kB", "999 kB", "1.0 MB", "9.9 MB", "10 MB"]
    assert [W.human(n) for n in (999_499_999, 1_000_000_000, 27_551_016_000)] == ["999 MB", "1.0 GB", "28 GB"]
    assert [W.human(n) for n in (2_500, 3_500, 1_250_000, 12_500_000)] == ["3 kB", "4 kB", "1.3 MB", "13 MB"]    # halves go up


def test_a_line_that_pins_no_version_is_said_to_be_weighed_at_its_latest():
    w = W.weigh(ask_from(Fake(ROUTES)), "PyPI", "leftpad-py", "1.2.0")
    assert W.part({**w, "of_version": "latest"}).startswith("for its latest version (the line pins none), with what it brings along, 3 packages")
    assert W.part({**w, "of_version": "pinned"}).startswith("with what it brings along")


def test_the_ci_job_weighs_the_first_found_dependency_and_the_thread_says_so():
    from test_registry import card, req
    routes = {"https://pypi.org/pypi/leftpad-py/json": (200, pypi_doc()), OSV: (200, {}), **ROUTES}
    fake = Fake(routes)
    (e,) = card([req("leftpad-py==1.2.0")], fake)["extras"]
    p = e["plain_facts"]["registry"]["packages"][0]
    assert p["weight"]["weight"] == "ok" and p["weight"]["of_version"] == "pinned" and p["weight"]["bytes"] == 30_012_000
    assert "with what it brings along, 3 packages (2 more than the line names) and about 30 MB to download on every fresh install" in e["thread_stub"]
    assert json.dumps(p)                      # the record stays plain JSON


def test_size_requests_reach_only_allowed_hosts():
    from urllib.parse import urlsplit
    for eco, name in (("PyPI", "requests"), ("npm", "@types/node")):
        assert urlsplit(W.size_request(eco, name, "1.0")[1]).hostname in RG.HOSTS
        assert urlsplit(W.graph_url(eco, name, "1.0")).hostname in RG.HOSTS


def test_of_two_files_in_the_same_tier_the_smaller_is_taken():
    assert W.pick_wheel([wheel("x", "1", 900), wheel("x", "1", 800, "py2.py3-none-any")])["size"] == 800


def test_a_pypi_name_is_normalised_before_the_graph_is_asked():
    from test_registry import card, req
    routes = {"https://pypi.org/pypi/leftpad-py/json": (200, pypi_doc(name="Leftpad_Py")), OSV: (200, {}), **ROUTES}
    fake = Fake(routes)
    card([req("Leftpad_Py==1.2.0")], fake)
    assert GRAPH in [c["url"] for c in fake.calls]


def test_the_weight_is_multiplied_by_this_projects_own_pipelines_and_says_without_a_cache():
    w = W.weigh(ask_from(Fake(ROUTES)), "PyPI", "leftpad-py", "1.2.0")
    w["pipelines"] = {"count": 918, "at_least": False, "days": 30}
    assert W.part(w).endswith("about 30 MB to download on every fresh install; this project ran 918 pipelines in the last 30 days, "
                              "so about 28 GB a month if each one installs it without a cache")
    w["pipelines"] = {"count": 1000, "at_least": True, "days": 30}
    assert "ran at least 1000 pipelines in the last 30 days, so at least" in W.part(w)
    for runs in (None, {"count": 0, "at_least": False, "days": 30}):
        w["pipelines"] = runs
        assert "pipelines" not in W.part(w)


def test_pipelines_are_counted_page_by_page_and_only_when_something_was_weighed():
    from itemator import ci
    from test_registry import req

    class Api:
        def __init__(self, pages):
            self.pages, self.paths = pages, []

        def get(self, path):
            self.paths.append(path)
            return self.pages.pop(0) if self.pages else []
    api = Api([[{}] * 100, [{}] * 18])
    assert ci.pipelines_run(api, 7, NOW) == {"count": 118, "at_least": False, "days": 30}
    assert api.paths[0] == "/projects/7/pipelines?created_after=2026-09-19T09:00:00Z&per_page=100&page=1" and len(api.paths) == 2
    assert ci.pipelines_run(Api([[{}] * 100] * 12), 7, NOW) == {"count": 1000, "at_least": True, "days": 30}

    class Down:
        def get(self, path):
            raise ci.JobError("HTTP 403")
    assert ci.pipelines_run(Down(), 7, NOW) is None

    asked = []
    routes = {"https://pypi.org/pypi/leftpad-py/json": (200, pypi_doc()), OSV: (200, {}), **ROUTES}
    rep = card_with([req("leftpad-py==1.2.0")], Fake(routes), lambda: asked.append(1) or {"count": 2, "at_least": False, "days": 30})
    assert asked == [1] and "this project ran 2 pipelines in the last 30 days" in rep["extras"][0]["thread_stub"]
    asked.clear()
    card_with([req("leftpad-py==1.2.0")], Fake({}), lambda: asked.append(1))
    assert asked == []                       # nothing weighed, nothing read


def card_with(files, fetch, pipelines):
    from itemator import ci
    from test_registry import ISSUE
    return ci.facts(mr_iid=5, mr_title="Fix the parser", mr_description="", mr_author_id=2, issues=[ISSUE],
                    issues_from="closes_issues", files=files, repo=None, base_sha="a", head_sha="b", warnings=[],
                    now=NOW, registry_fetch=fetch, pipelines=pipelines)


def test_a_graph_of_exactly_the_cap_is_not_at_least_and_unknown_sizes_make_the_month_at_least(monkeypatch):
    monkeypatch.setattr(W, "MAX_NODES", 3)
    w = W.weigh(ask_from(Fake(ROUTES)), "PyPI", "leftpad-py", "1.2.0")
    assert (w["packages"], w["of"], w["capped"]) == (3, 3, False) and "at least" not in W.part(w)
    routes = {k: v for k, v in ROUTES.items() if "big" not in k}
    w = W.weigh(ask_from(Fake(routes)), "PyPI", "leftpad-py", "1.2.0")
    w["pipelines"] = {"count": 10, "at_least": False, "days": 30}
    assert W.part(w).endswith("this project ran 10 pipelines in the last 30 days, so at least 120 kB a month if each one installs it without a cache")
