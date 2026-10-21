"""New powers in code: a changed source file that now reaches the network, runs other programs, reads the environment
or key files, or runs code it builds at run time, when the same file did none of that before the change.

The rules read file kinds, not code (an outside reviewer's first point). This reads code, with no model: each added
line is matched against a short list of calls per power, and a power counts only when the file's text at the base
commit (or its removed and context lines, when no base text is given) shows no call of that power at all. A new file
has no base text, so everything it can do is new. Tests, docs, generated and vendored files are not read.

It is information for the card's "Also checked" line, never an extra: an API client that gains one more request is
ordinary, and the line lets the reviewer see in one sentence that a file's reach grew.
"""
from __future__ import annotations

import re
import subprocess

from itemator import extras as X
from itemator import shapes as SH

MAX_TEXT = 80
SHOWN = 3
_SOURCE = {"py", "js", "jsx", "ts", "tsx", "mjs", "cjs", "go", "rb", "rs", "java", "kt", "php", "cs", "sh", "bash"}
POWERS = {
    "network": ("reaches the network", re.compile(
        r"\brequests\.(?:get|post|put|patch|delete|head|request|Session)\b|\burllib\.request\b|\burlopen\(|\bhttp\.client\b"
        r"|\bsocket\.(?:socket|create_connection)\(|\bhttpx\.|\baiohttp\.ClientSession\b|\bfetch\(|\baxios\b"
        r"|\bXMLHttpRequest\b|\bnew WebSocket\(|\bhttps?\.(?:request|get)\(|\bnet\.(?:connect|createConnection|Dial\w*)\("
        r"|\bhttp\.(?:Get|Post|PostForm|NewRequest\w*)\(|\bNet::HTTP\b|\breqwest::|\bHttpClient\b|\bcurl_exec\(")),
    "process": ("runs other programs", re.compile(
        r"\bsubprocess\.|\bos\.(?:system|popen|exec\w*|spawn\w*)\(|\bpty\.spawn\(|\bchild_process\b|\b(?:execSync|execFileSync"
        r"|spawnSync)\(|\bexec\.Command(?:Context)?\(|\bCommand::new\(|\bRuntime\.getRuntime\(\)\.exec|\bProcessBuilder\("
        r"|\bProcess\.Start\(|\bshell_exec\(|\bproc_open\(")),
    "environment": ("reads the whole environment or a key file", re.compile(
        r"\bdict\(os\.environ\)|\bos\.environ\.(?:copy|items|keys|values)\(\)|\bos\.environ\)|JSON\.stringify\(process\.env\)"
        r"|\bObject\.(?:entries|keys|values|assign)\([^)]*process\.env\b|\.\.\.process\.env\b|\bos\.Environ\(\)|\benv::vars\(\)"
        r"|\bSystem\.getenv\(\)|\bENV\.to_h\b|~/\.ssh|\.aws/credentials|\bid_rsa\b|\.npmrc\b|\.netrc\b|\.pypirc\b"
        r"|\.docker/config\.json|\.kube/config")),
    "dynamic": ("runs code it builds at run time", re.compile(
        r"(?<![\w.])eval\(|(?<![\w.])exec\(|\bnew Function\(|\bpickle\.loads?\(|\bmarshal\.loads\(|\b__import__\("
        r"|\bimportlib\.import_module\(|\bvm\.runIn\w+\(|\bFunction\(\s*['\"]")),
}


def _code(text: str) -> bool:
    s = text.strip()
    return bool(s) and not s.startswith(("#", "//", "/*", "*", "--"))


_TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "testing", "e2e"}
_BUILT = {"dist", "build", "out", "target", "vendor", "node_modules"}


def readable(path: str) -> bool:
    dirs = [d.lower() for d in path.split("/")[:-1]]
    return (X._ext(path) in _SOURCE and not X.is_test_file(path) and not X.is_generated(path) and not X._exempt(path)
            and not set(dirs) & (_TEST_DIRS | _BUILT) and not any(d.startswith(".") and "build" in d for d in dirs))


def find(files: list[dict], before: dict | None = None) -> list[dict]:
    """[{path, power, line, text}]: the first added line per new power per file. `before`: {path: the file's text at the
    base commit, "" for a new file}; for a path not in it, the patch's removed and context lines stand in."""
    out = []
    for f in files:
        path = f.get("filename") or ""
        if f.get("status") == "removed" or not f.get("patch") or not readable(path):
            continue
        rows = list(X._lines(f["patch"]))
        if before is not None and path in before:
            old = before[path]
        else:
            old = "" if f.get("status") == "added" else "\n".join(t for s, t in rows if s in ("-", " "))
        seen = set()
        for n, t in SH.added(f["patch"]):
            if not _code(t):
                continue
            for power, (_, rx) in POWERS.items():
                if power in seen or not rx.search(t) or rx.search(old):
                    continue
                seen.add(power)
                out.append({"path": path, "power": power, "line": n, "text": t.strip()[:MAX_TEXT]})
    return out


def read_before(repo_dir: str, base: str, files: list[dict]) -> dict:
    """{path: text at `base`} for the readable changed files; "" for an added one; a file git cannot show is left out."""
    out = {}
    for f in files:
        path = f.get("filename") or ""
        if not readable(path) or f.get("status") == "removed":
            continue
        if f.get("status") == "added":
            out[path] = ""
            continue
        r = subprocess.run(["git", "-C", repo_dir, "show", f"{base}:{f.get('previous_filename') or path}"],
                           capture_output=True, text=True, errors="replace", timeout=30)
        if r.returncode == 0:
            out[path] = r.stdout
    return out


def sentence(found: list[dict]) -> str:
    parts = [f"`{d['path']}` line {d['line']} now {POWERS[d['power']][0]} (`{d['text']}`)" for d in found[:SHOWN]]
    more = f"; and {len(found) - SHOWN} more" if len(found) > SHOWN else ""
    return "Code that can do something new, which the same file did not do before: " + "; ".join(parts) + more + "."
