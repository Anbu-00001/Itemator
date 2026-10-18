"""examples/make_example.py: the staged change behind the routing picture lands each file where it should."""
import importlib.util
import json
import pathlib

SPEC = importlib.util.spec_from_file_location("make_example", pathlib.Path(__file__).resolve().parent.parent / "examples" / "make_example.py")
ME = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ME)


def test_the_staged_change_has_a_file_in_four_bins_and_a_hidden_program(tmp_path):
    out = tmp_path / "t.json"
    assert ME.main(["make_example.py", str(out)]) == 0
    d = json.loads(out.read_text())
    got = {f["path"]: f["landing"] for f in d["files"]}
    assert got == {".github/workflows/ci.yml": "listed", "README.md": "ordinary", "greeting.py": "ordinary", "logo.png": "listed",
                   "parse.py": "noted", "report.pdf": "listed", "requirements.txt": "listed", "tidy.py": "neutral", "utils.py": "noted"}
    pdf = [f for f in d["files"] if f["path"] == "report.pdf"][0]
    assert "name says pdf" in pdf["route"][3]["say"]                                  # the opener noticed what the name hides
    by = {f["path"]: f for f in d["files"]}
    assert "never changed in the same commit" in by["utils.py"]["route"][4]["say"]    # the stranger
    assert "Fix crash when text is None" in by["parse.py"]["route"][5]["say"]         # the deleted fence
    again = tmp_path / "u.json"
    ME.main(["make_example.py", str(again)])
    strip = lambda x: {k: v for k, v in x.items() if k != "source"}
    assert strip(json.loads(again.read_text())) == strip(d)                            # same files and routes every time
