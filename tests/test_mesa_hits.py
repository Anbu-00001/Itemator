"""eval/mesa_hits.py: the sample is seeded, a subset of the hits, and the same every time."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import mesa_hits as H  # noqa: E402


def rows(n):
    return [{"commit": f"{i:040x}", "said": {}} for i in range(n)]


def test_the_sample_is_a_seeded_subset_of_the_hits():
    r = rows(100)
    s = H.sample(r)
    assert len(s) == 25 and set(s) <= {x["commit"] for x in r}
    assert s == H.sample(list(reversed(r)))              # the order the hits arrive in does not matter
    assert s != H.sample(r[:99])                         # but which hits exist does


def test_a_short_list_is_taken_whole():
    assert sorted(H.sample(rows(7))) == sorted(x["commit"] for x in rows(7))
    assert H.sample([]) == []
