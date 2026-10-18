"""eval/advisory_replay.py: turning a fixing commit round so the checks see the vulnerable lines as added ones."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import advisory_replay as AR  # noqa: E402

FIX = ("@@ -10,4 +10,5 @@ jobs:\n"
       "     steps:\n"
       '-      - run: echo "${{ github.event.issue.title }}"\n'
       "+      - env:\n"
       "+          TITLE: ${{ github.event.issue.title }}\n"
       '+        run: echo "$TITLE"\n'
       "     - uses: x\n")
FILE = {"filename": ".github/workflows/a.yml", "status": "modified", "patch": FIX}


def test_the_patch_is_turned_round_with_its_ranges():
    back = AR.reverse_patch(FIX)
    assert back.split("\n")[0] == "@@ -10,5 +10,4 @@ jobs:"
    assert '+      - run: echo "${{ github.event.issue.title }}"' in back and "-      - env:" in back and "     steps:" in back
    assert AR.reverse_patch(back) == FIX


def test_a_deleted_file_becomes_an_added_one():
    assert AR.turned_round([{"filename": "a", "status": "removed", "patch": "@@ -1,2 +0,0 @@\n-x\n-y\n"}]) == [{"filename": "a", "status": "added", "patch": "@@ -0,0 +1,2 @@\n+x\n+y\n"}]


def test_the_vulnerable_version_is_caught_and_the_fix_is_silent_and_no_diff_text_is_kept():
    r = AR.summarise({"advisory": "A", "repo": "o/r", "fix": "a" * 40}, [FILE])
    assert r["caught"] and r["silent_on_fix"] and r["fix"] == "a" * 12
    assert r["vulnerable_diff"]["untrusted"] == [{"path": ".github/workflows/a.yml", "line": 11, "kind": "github-expression"}]
    assert "text" not in str(r)


def test_a_fix_that_still_pastes_the_text_is_named_on_the_fix_too():
    bad = {**FILE, "patch": FIX.replace("TITLE: ${{ github.event.issue.title }}", 'X: 1\n+        run: echo "${{ github.event.issue.body }}"')}
    assert not AR.summarise({"advisory": "A", "repo": "o/r", "fix": "b" * 40}, [bad])["silent_on_fix"]
