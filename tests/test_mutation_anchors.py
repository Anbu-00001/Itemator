"""Every mutant of the manual mutation-suite job still names exactly one place in the code. The job runs by hand, so an anchor
that a later change moved went unnoticed until the job failed (2026-10-20: 10 of 550 in eval/mutate_ci.py); this runs in
every pipeline and takes about a second."""
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("script", ["mutate_extras.py", "mutate_ci.py", "mutate_checks.py"])
def test_every_mutant_anchor_is_found_once(script, tmp_path):
    r = subprocess.run([sys.executable, "-I", str(ROOT / "eval" / script), str(ROOT), str(tmp_path / "w"), "--anchors-only"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout[-500:] + r.stderr[-1500:]
    assert "anchors found" in r.stdout
