"""Label packets put the listed extras' files first, so a long diff never cuts what the labellers must read."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import label_packets as P  # noqa: E402


def f(name, size=10):
    return {"filename": name, "status": "modified", "patch": "+" * size + "\n"}


def test_listed_files_and_directories_come_first_and_the_root_marks_nothing():
    files = [f("a.rb"), f("b.rb"), f("spec/x_spec.rb"), f("z.toml")]
    order = lambda text: [line.split()[1] for line in text.splitlines() if line.startswith("### ")]
    assert order(P.diff_text(files, {"z.toml"})) == ["z.toml", "a.rb", "b.rb", "spec/x_spec.rb"]
    assert order(P.diff_text(files, {"spec/"})) == ["spec/x_spec.rb", "a.rb", "b.rb", "z.toml"]
    assert order(P.diff_text(files, {"./", "z.toml"})) == ["z.toml", "a.rb", "b.rb", "spec/x_spec.rb"]
    assert "z.toml (modified)  <- LISTED EXTRA" in P.diff_text(files, {"z.toml"})


def test_the_size_limits_cut_the_rest_not_the_listed_file():
    files = [f(f"f{i}.rb", P.FILE_LIMIT * 2) for i in range(20)] + [f("late.toml")]
    text = P.diff_text(files, {"late.toml"})
    assert text.startswith("### late.toml") and "more characters cut" in text and "more files not shown" in text
    assert len(text) <= P.TOTAL_LIMIT + 200
