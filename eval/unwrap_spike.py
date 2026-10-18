"""Spike for the unwrap tool (itemator/unwrap.py), pre-registered in eval/unwrap_spike_rubric.json.
Part A: the two xz-utils test files from the 2024 backdoor (tukaani-project/xz, tag v5.6.0), shown as the rules describe
them. Part B: for binary or large files that AIDev agent pull requests ADDED, does the kind the rules read from the
first bytes agree with file(1), the standard tool? Read-only GETs through `gh api`; file contents stay in
eval/cache/unwrap/ (gitignored); the result holds pull request addresses, extensions, kinds, mime types and note
categories only.

usage: python3 eval/unwrap_spike.py [--want 100] [--out results/unwrap_spike_v1.json]"""
from __future__ import annotations

import argparse, base64, collections, json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import unwrap as U  # noqa: E402

CASES = ROOT / "eval" / "unwrap_spike_cases.json"
CACHE = ROOT / "eval" / "cache" / "unwrap"
XZ_FILES = ("tests/files/bad-3-corrupt_lzma2.xz", "tests/files/good-large_compressed.lzma")
MAX_BYTES = 1_000_000          # the contents API returns a file up to 1 MB
WANT = 100

ACCEPT = {
    "elf": ("application/x-executable", "application/x-sharedlib", "application/x-pie-executable", "application/x-object", "application/x-coredump"),
    "pe": ("application/vnd.microsoft.portable-executable", "application/x-dosexec"),
    "macho": ("application/x-mach-binary",), "wasm": ("application/wasm",),
    "java_class": ("application/x-java-applet", "application/x-java"),
    "png": ("image/png",), "jpeg": ("image/jpeg",), "gif": ("image/gif",),
    "zip": ("application/zip", "application/java-archive", "application/epub+zip", "application/vnd.android.package-archive",
            "application/vnd.openxmlformats-officedocument.", "application/x-zip"),
    "gzip": ("application/gzip", "application/x-gzip"), "bzip2": ("application/x-bzip2",), "xz": ("application/x-xz",),
    "lzma": ("application/x-lzma",), "tar": ("application/x-tar",), "pdf": ("application/pdf",),
    "script": ("text/x-shellscript", "text/x-script.", "text/x-python", "text/x-perl", "text/x-ruby", "text/x-env"),
    "text": ("text/", "application/json", "application/xml", "application/javascript", "image/svg+xml", "application/x-ndjson"),
    "empty": ("inode/x-empty", "application/x-empty"),
}
GENERIC = ("application/octet-stream",)


def agrees(kind: str, mime: str) -> bool:
    return any(mime == a or (a.endswith(("/", ".")) and mime.startswith(a)) for a in ACCEPT.get(kind, ()))


def verdict(kind: str, mime: str) -> str:
    """agree: both name the same format. both_generic: the rules know no format and file(1) says plain data.
    unknown_to_the_rules: the rules know no format but file(1) names one. disagree: anything else."""
    if agrees(kind, mime):
        return "agree"
    if kind == "unknown_binary":
        return "both_generic" if mime in GENERIC else "unknown_to_the_rules"
    return "disagree"


NOTE_CATEGORIES = (("the name says", "name_disagrees"), ("leaves its folder", "entry_leaves_folder"), ("encrypted entries", "encrypted_entries"),
                   ("unpacks to a program", "unpacks_to_program"), ("is a program or script", "program_entries"), ("are programs or scripts", "program_entries"), ("nested archive", "nested_archives"),
                   ("unpacks to", "unpacks_to_huge"), ("high entropy", "high_entropy"), ("does not read", "entry_unreadable"),
                   ("follow the end of the image", "after_image"), ("follow the end of the stream", "after_stream"),
                   ("does not decode", "broken"), ("cut short", "broken"), ("does not open", "broken"), ("damaged", "broken"))


def note_category(note: str) -> str:
    """A note's category, so the result file never repeats an entry name from someone else's archive."""
    return next((label for key, label in NOTE_CATEGORIES if key in note), "other")


def summarize(rows: list[dict], examined: int) -> dict:
    by = collections.Counter(r["verdict"] for r in rows)
    pairs = collections.Counter((r["kind"], r["mime"]) for r in rows if r["verdict"] in ("disagree", "unknown_to_the_rules"))
    return {"pull_requests_examined": examined, "files_read": len(rows),
            "by_verdict": {v: by.get(v, 0) for v in ("agree", "both_generic", "unknown_to_the_rules", "disagree")},
            "share_agree_or_both_generic": round((by["agree"] + by["both_generic"]) / len(rows), 4) if rows else None,
            "by_kind": dict(sorted(collections.Counter(r["kind"] for r in rows).items())),
            "files_with_a_note": sum(bool(r["notes"]) for r in rows),
            "notes_by_category": dict(sorted(collections.Counter(c for r in rows for c in r["notes"]).items())),
            "differences": [{"rules": k, "file": m, "files": n} for (k, m), n in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))]}


def gh(path: str, retries: int = 3):
    f = CACHE / (path.replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "_") + ".json")
    if f.exists():
        return json.loads(f.read_text())
    for i in range(retries):
        r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
        if r.returncode == 0:
            CACHE.mkdir(parents=True, exist_ok=True)
            f.write_text(r.stdout)
            return json.loads(r.stdout)
        if "HTTP 4" in r.stderr and "429" not in r.stderr and "403" not in r.stderr:
            return None
        time.sleep(5 * (i + 1))
    return None


def opaque_added(f: dict) -> bool:
    """A file the pull request added that GitHub shows no text patch for (binary, or too large to show)."""
    return f["status"] == "added" and not f.get("patch") and bool(f.get("contents_url"))


def blob(contents_url: str) -> bytes | None:
    d = gh(contents_url.split("api.github.com/", 1)[1])
    if not d or d.get("encoding") != "base64" or d.get("size", 0) > MAX_BYTES:
        return None
    return base64.b64decode(d["content"])


def file_mime(data: bytes) -> str:
    r = subprocess.run(["file", "-b", "--mime-type", "-"], input=data, capture_output=True)
    return r.stdout.decode("utf-8", "replace").strip() or "unknown"


def part_a() -> list[dict]:
    out = []
    for p in XZ_FILES:
        d = gh(f"repos/tukaani-project/xz/contents/{p}?ref=v5.6.0")
        if not d or d.get("encoding") != "base64":
            out.append({"path": p, "fetched": False})
            continue
        data = base64.b64decode(d["content"])
        v = U.look(data, p)
        out.append({"path": p, "fetched": True, "bytes": len(data), "file_mime": file_mime(data), "kind": v.kind, "line": v.line()})
    return out


def part_b(want: int) -> tuple[list[dict], int]:
    rows, examined = [], 0
    for c in json.loads(CASES.read_text())["cases"]:
        if len(rows) >= want:
            break
        examined += 1
        repo = "/".join(c["html_url"].split("/")[3:5])
        files = gh(f"repos/{repo}/pulls/{c['number']}/files?per_page=100")
        for f in files or []:
            if len(rows) >= want:
                break
            if not opaque_added(f):
                continue
            data = blob(f["contents_url"])
            if data is None:
                continue
            v = U.look(data, f["filename"])
            mime = file_mime(data)
            ext = f["filename"].rsplit(".", 1)[-1].lower() if "." in f["filename"].rsplit("/", 1)[-1] else ""
            rows.append({"pr_id": c["pr_id"], "agent": c["agent"], "html_url": c["html_url"], "ext": ext, "bytes": len(data),
                         "kind": v.kind, "mime": mime, "verdict": verdict(v.kind, mime), "notes": sorted(note_category(n) for n in v.notes)})
        if examined % 25 == 0:
            print(f"{examined} examined, {len(rows)} files", file=sys.stderr, flush=True)
    return rows, examined


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--want", type=int, default=WANT)
    ap.add_argument("--out", default=str(ROOT / "results" / "unwrap_spike_v1.json"))
    a = ap.parse_args()
    rows, examined = part_b(a.want)
    out = {"rubric": "eval/unwrap_spike_rubric.json", "summary": summarize(rows, examined), "xz_files": part_a(), "files": rows}
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out["summary"]))


if __name__ == "__main__":
    main()
