"""Copies what the Space needs into a folder (python3 tools/hf_runner_stage.py OUT): the runner, the rules package, the eval
scripts and the leg-2 frame. Never the caches. Then: hf upload Anbu-00001/Sentinel OUT . --repo-type space"""
import pathlib, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PARTS = [("itemator", "itemator"), ("eval", "eval"), ("hf_runner", "hf_runner"), ("results/aidev_revert_frame.json", "results/aidev_revert_frame.json")]
SKIP = shutil.ignore_patterns("cache", "__pycache__", "*.pyc", "*.part")


def stage(out):
    out = pathlib.Path(out)
    for src, dst in PARTS:
        s, d = ROOT / src, out / dst
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(s, d, ignore=SKIP, dirs_exist_ok=True) if s.is_dir() else shutil.copy2(s, d)
    shutil.copy2(ROOT / "hf_runner" / "Dockerfile", out / "Dockerfile")
    shutil.copy2(ROOT / "hf_runner" / "README.md", out / "README.md")
    return sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())


if __name__ == "__main__":
    files = stage(sys.argv[1])
    print(len(files), "files")
