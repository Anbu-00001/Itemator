"""What the check costs against what one `remove` saves, by the same per-install arithmetic (eval/sci_spent.py); no network."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import sci_spent as S  # noqa: E402
from itemator.sci import per_install  # noqa: E402

INPUTS = {"job_seconds": [30.0, 34.0, 40.0], "clone_bytes": 3_000_000, "image_compressed_bytes": 400_000_000}


def saved(mb):
    g = per_install(mb, (1.21, 1.65))
    return {e: {"sci_g_per_install": g[e]["sci_g_per_install"]} for e in ("low", "high")}


def test_the_check_is_priced_as_an_install_of_its_clone_and_image_for_its_median_seconds():
    got = S.compute(INPUTS, {"live": saved(31), "median": saved(0.57)})
    cached, pulled = per_install(3.0, (34.0, 34.0)), per_install(403.0, (34.0, 34.0))
    assert got["inputs"] == {"jobs": 3, "median_job_seconds": 34.0, "clone_mb": 3.0, "image_mb": 400}
    assert got["spent_g_per_check"]["image_cached"]["high"] == round(cached["high"]["sci_g_per_install"], 4)
    assert got["spent_g_per_check"]["image_pulled"]["low"] == round(pulled["low"]["sci_g_per_install"], 3)


def test_repaying_a_check_takes_more_installs_of_a_small_dependency_and_of_a_pulled_image():
    got = S.compute(INPUTS, {"live": saved(31), "median": saved(0.57)})
    live, med = got["installs_to_repay_one_check_live"], got["installs_to_repay_one_check_median"]
    for e in ("low", "high"):
        assert med["image_cached"][e] > live["image_cached"][e] and live["image_pulled"][e] > live["image_cached"][e]
        assert live["image_pulled"][e] == round(got["spent_g_per_check"]["image_pulled"][e] / got["saved_g_per_install_live"][e], 1)
    assert "model calls" in got["left_out"]


def test_the_committed_result_matches_its_inputs():
    for version in sorted(S.VERSIONS):
        inputs, out = S.paths(version)
        assert S.compute(json.loads(inputs.read_text()), json.loads((S.RES / "sci_estimate_v1.json").read_text())) == json.loads(out.read_text())


def test_apt_downloads_count_on_every_run_even_with_the_image_cached():
    got = S.compute(dict(INPUTS, apt_bytes=24_000_000, image="python:3.12-slim"), {"live": saved(31), "median": saved(0.57)})
    cached, pulled = per_install(27.0, (34.0, 34.0)), per_install(427.0, (34.0, 34.0))
    assert got["spent_g_per_check"]["image_cached"]["high"] == round(cached["high"]["sci_g_per_install"], 4)
    assert got["spent_g_per_check"]["image_pulled"]["low"] == round(pulled["low"]["sci_g_per_install"], 3)
    assert got["inputs"]["apt_mb"] == 24.0 and got["inputs"]["image"] == "python:3.12-slim" and got["inputs"]["clone_mb"] == 3.0
    assert "apt_mb" not in S.compute(INPUTS, {"live": saved(31), "median": saved(0.57)})["inputs"]


def test_v2_reads_only_jobs_after_the_switch_and_uses_the_slim_image():
    v1, v2 = (json.loads(S.paths(v)[0].read_text()) for v in (1, 2))
    assert v2["image"] == "python:3.12-slim" and v2["apt_bytes"] > 0 and min(v2["job_ids"]) > max(v1["job_ids"])
    assert S.VERSIONS[2]["after"] > v1["read_at"] and S.VERSIONS[1]["after"] == ""


def test_fetch_keeps_only_itemator_jobs_after_the_switch(monkeypatch):
    import io
    import subprocess
    import types
    jobs = [{"id": 1, "name": "itemator", "duration": 30.0, "created_at": "2026-10-21T05:00:00Z"},
            {"id": 2, "name": "itemator", "duration": 25.0, "created_at": "2026-10-21T06:00:00Z"},
            {"id": 3, "name": "tests", "duration": 9.0, "created_at": "2026-10-21T06:00:00Z"}]

    def run(cmd, **kw):
        if cmd[0] == "git":
            pack = pathlib.Path(cmd[-1], "objects", "pack")
            pack.mkdir(parents=True)
            (pack / "p.pack").write_bytes(b"x" * 10)
            return subprocess.CompletedProcess(cmd, 0)
        page = int(cmd[-1].rsplit("page=", 1)[1])
        return types.SimpleNamespace(stdout=json.dumps(jobs if page == 1 else []))
    monkeypatch.setattr(S.subprocess, "run", run)
    monkeypatch.setattr(S.urllib.request, "urlopen", lambda url, timeout: io.StringIO(json.dumps(
        {"images": [{"architecture": "amd64", "os": "linux", "size": 43_000_000}]})))
    got = S.fetch(2)
    assert got["job_ids"] == [2] and got["job_seconds"] == [25.0] and got["clone_bytes"] == 10
    assert got["apt_bytes"] == 23_800_000 and got["image"] == "python:3.12-slim" and got["image_compressed_bytes"] == 43_000_000
    assert S.fetch(1)["job_ids"] == [1, 2] and S.fetch(1)["apt_bytes"] == 0


def test_v3_reads_only_jobs_after_the_alpine_switch():
    v2, v3 = (json.loads(S.paths(v)[0].read_text()) for v in (2, 3))
    assert v3["image"] == "python:3.12-alpine" and min(v3["job_ids"]) > max(v2["job_ids"]) and S.VERSIONS[3]["after"] > S.VERSIONS[2]["after"]


def test_v3_counts_the_git_download_the_alpine_trial_measured():
    trial = json.loads((S.RES / "alpine_trial_v1.json").read_text())["downloaded_per_run_bytes"]["alpine-trial (apk git)"]
    assert S.VERSIONS[3]["apt_bytes"] == trial == json.loads(S.paths(3)[0].read_text())["apt_bytes"]
