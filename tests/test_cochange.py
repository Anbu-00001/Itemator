"""itemator/cochange.py: which files in a change have never changed together with the others."""
from itemator import cochange as C
from itemator.cochange import strangers


def test_a_file_that_shares_no_commit_is_the_stranger():
    h = {"a.py": ["c1", "c2", "c3"], "b.py": ["c1", "c4", "c5"], "c.py": ["c2", "c6", "c7"], "z.py": ["z1", "z2", "z3"]}
    assert strangers(h) == {"a.py": C.PARTNERED, "b.py": C.PARTNERED, "c.py": C.PARTNERED, "z.py": C.STRANGER}


def test_few_commits_means_too_new_not_stranger():
    h = {"a.py": ["c1", "c2", "c3"], "b.py": ["c1", "c4", "c5"], "c.py": ["c2", "c6", "c7"], "n.py": ["n1", "n2"]}
    assert strangers(h)["n.py"] == C.TOO_NEW
    assert strangers({**h, "n.py": ["n1", "n2", "n3"]})["n.py"] == C.STRANGER      # exactly MIN_HISTORY counts


def test_a_commit_in_most_files_is_a_sweep_and_dropped():
    sweep = ["s"]
    h = {"a.py": sweep + ["a1", "a2"], "b.py": sweep + ["b1", "b2"], "c.py": sweep + ["c1", "c2"]}
    assert set(strangers(h).values()) == {C.STRANGER}                               # sharing only "s" says nothing
    h2 = {"a.py": ["s", "k", "a2"], "b.py": ["s", "k", "b2"], "c.py": ["s", "c1", "c2"], "d.py": ["d1", "d2", "d3"]}
    assert strangers(h2)["a.py"] == C.PARTNERED and strangers(h2)["c.py"] == C.STRANGER


def test_exactly_half_is_not_a_sweep():
    h = {"a.py": ["s", "a1", "a2"], "b.py": ["s", "b1", "b2"], "c.py": ["c1", "c2", "c3"], "d.py": ["d1", "d2", "d3"]}
    assert strangers(h)["a.py"] == C.PARTNERED and strangers(h)["b.py"] == C.PARTNERED


def test_fewer_than_three_files_with_history_is_not_enough():
    h = {"a.py": ["c1", "c2", "c3"], "b.py": ["c1", "c2", "c3"], "new.py": []}
    assert strangers(h) == {"a.py": C.NOT_ENOUGH, "b.py": C.NOT_ENOUGH, "new.py": C.NOT_ENOUGH}
    assert strangers({}) == {}


def test_repeated_ids_do_not_inflate_history():
    h = {"a.py": ["c1", "c1", "c1"], "b.py": ["c2", "c3", "c4"], "c.py": ["c5", "c6", "c7"]}
    assert strangers(h)["a.py"] == C.TOO_NEW


def test_the_same_input_gives_the_same_answer():
    h = {"a.py": ["c1", "c2", "c3"], "b.py": ["c1", "c4", "c5"], "c.py": ["c2", "c6", "c7"]}
    assert strangers(h) == strangers(dict(reversed(list(h.items()))))


def test_three_of_five_is_a_sweep_and_two_of_five_is_not():
    five = {f"{n}.py": [f"{n}1", f"{n}2", f"{n}3"] for n in "abcde"}
    three = {k: (v + ["s"] if k[0] in "abc" else v) for k, v in five.items()}
    two = {k: (v + ["s"] if k[0] in "ab" else v) for k, v in five.items()}
    assert strangers(three)["a.py"] == C.STRANGER      # "s" is in 3 of 5 files: dropped
    assert strangers(two)["a.py"] == C.PARTNERED       # "s" is in 2 of 5 files: kept
