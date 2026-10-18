"""Run Itemator's rules on your own machine: `python -m itemator.local --issue issue.txt [--base main] [--head HEAD]`.

No GitLab, no network, no model and nothing is posted. It reads the git diff from BASE to HEAD (default: the merge
base with `main`, to HEAD) and the issue text (a file, `-` for standard input, or `--issue-text "..."`), runs the same
fixed rules the CI job runs (itemator/extras.py), and prints each extra with the reason the rules gave. Output is the
same for the same inputs. A new dependency is not looked up in its registry here: the CI job does that, so a package
shows up as an extra without its registry facts.

Exit 0 always when it ran; exit 2 when git or the arguments are wrong. `--commits` reads the commit messages from BASE to HEAD as the request, for a change with no issue (an agent's local commits). `--map` adds a table of every changed file (lines added and removed, and why each was or was not listed; a Python file whose change is provably only layout or comments says so, and an added binary file says what it is from its bytes). `--lint-policy` checks the team's .itemator.toml instead
(every ignore entry has a reason, no dead path pattern) and exits 1 when there is something to tidy. The facts are information, not a verdict.
Standard library only."""
from __future__ import annotations

import argparse
import subprocess
import sys

from itemator import ci
from itemator import extras as X
from itemator import neutral as N
from itemator import policy as POL
from itemator import unwrap as U


def merge_base(repo: str, branch: str, head: str) -> str:
    out = subprocess.run(["git", "-C", repo, "merge-base", branch, head], capture_output=True, text=True)
    if out.returncode != 0:
        raise ci.JobError(f"no merge base between {branch} and {head}: {out.stderr.strip() or 'unknown ref'}")
    return out.stdout.strip()


def commit_messages(repo: str, base: str, head: str) -> str:
    """The messages of the commits from BASE to HEAD, oldest first: the request an agent's commits claim to answer."""
    out = subprocess.run(["git", "-C", repo, "log", "--reverse", "--format=%B", f"{base}..{head}"], capture_output=True)
    if out.returncode != 0:
        raise ci.JobError(f"git log failed: {out.stderr.decode('utf-8', 'replace').strip() or 'unknown ref'}")
    return out.stdout.decode("utf-8", "replace")


def render(analysis: X.Analysis, n_files: int, issue_given: bool, source: str = "issue text") -> str:
    lines = [f"Itemator rules v{X.RULES_VERSION}: {n_files} changed file(s), "
             f"{source + ' read' if issue_given else 'no ' + source + ' given (every kind of extra is judged without a request to compare)'}."]
    if not analysis.extras:
        lines.append("No extras: nothing in this change falls outside what the issue text names.")
    for e in analysis.extras:
        where = f" {e.path}" if e.path else ""
        lines.append(f"- {e.kind}{where}: {e.why}")
        for d in e.detail:
            if isinstance(d, str):
                lines.append(f"    {d}")
    if analysis.unplaced:
        lines.append(f"Could not place {len(analysis.unplaced)} file(s) against the issue: " + ", ".join(analysis.unplaced[:10]))
    return "\n".join(lines)


MAX_READ = 4 * 1024 * 1024


def _blob(repo: str, ref: str, path: str) -> bytes | None:
    out = subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"], capture_output=True)
    return out.stdout if out.returncode == 0 and len(out.stdout) <= MAX_READ else None


def neutral_verdict(repo: str, base: str, head: str, f: dict) -> N.Verdict | None:
    """What itemator.neutral says about a modified .py file; None for any other file or one that cannot be read."""
    if not f["filename"].endswith(".py"):
        return None
    old, new = _blob(repo, base, f["filename"]), _blob(repo, head, f["filename"])
    if old is None or new is None:
        return None
    try:
        return N.classify(old.decode("utf-8"), new.decode("utf-8"))
    except UnicodeDecodeError:
        return None


def opened(repo: str, head: str, f: dict) -> U.Look | None:
    """What itemator.unwrap says about an added or changed binary file, from its own bytes; None for any other file."""
    if not f.get("binary") or f.get("status", "modified") not in ("added", "modified"):
        return None
    data = _blob(repo, head, f["filename"])
    return U.look(data, f["filename"]) if data is not None else None


def file_facts(repo: str, base: str, head: str, files: list[dict]) -> dict[str, str]:
    """What two checks that need no request can say about a file: a modified .py file whose change is provably only
    layout, comments, docstrings or plain-function order (itemator/neutral.py), and what an added or changed binary file
    is from its own bytes (itemator/unwrap.py). A file neither check can say anything about gets no entry."""
    facts: dict[str, str] = {}
    for f in files:
        v = neutral_verdict(repo, base, head, f)
        if v is not None and v.level in N.PROVED:
            facts[f["filename"]] = f"checked: {v.reason}"
        look = opened(repo, head, f)
        if look is not None:
            facts[f["filename"]] = "opened: " + look.line()
    return facts


PLACED_LABELS = {"unplaced": "not placed against the request", "named": "matches a word in the request",
                 "none": "no match in the request, and no rule lists it"}


def placement(analysis: X.Analysis, files: list[dict]) -> dict[str, tuple[str, list[str]]]:
    """For each changed file: how the request rules placed it ("listed" with the kinds of extra that list it,
    "unplaced", "named" by a word of the request, or "none") -- the facts the reviewer's map and the trace both print."""
    kinds: dict[str, list[str]] = {}
    for e in analysis.extras:
        for path in ([e.path] if e.path else []) + [d.split(" ")[0] for d in e.detail if isinstance(d, str)]:
            kinds.setdefault(path, []).append(e.kind)
    named, unplaced = set(analysis.named_paths), set(analysis.unplaced)
    out = {}
    for f in files:
        name = f["filename"]
        if name in kinds:
            out[name] = ("listed", list(dict.fromkeys(kinds[name])))
        else:
            out[name] = ("unplaced" if name in unplaced else "named" if name in named else "none", [])
    return out


def file_map(analysis: X.Analysis, files: list[dict], facts: dict[str, str] | None = None) -> str:
    """A reviewer's map: every changed file with its added and removed lines and one plain label, so a reviewer of a
    large, machine-made change sees where to look first. The label states which rule listed the file, never a verdict;
    a file that is neither matched by a word of the request nor listed is labelled as such, not as fine."""
    placed = placement(analysis, files)
    rows = []
    for f in files:
        name = f["filename"]
        how, kinds = placed[name]
        label = "extra: " + ", ".join(kinds) if how == "listed" else PLACED_LABELS[how]
        if facts and name in facts:
            label += "; " + facts[name]
        rows.append((f"{f.get('status', 'modified')} {name}", f"+{f.get('additions', 0)} -{f.get('deletions', 0)}"
                     + (" binary" if f.get("binary") else ""), label))
    width = max((len(r[0]) for r in rows), default=0)
    lines = [f"Reviewer's map: {len(rows)} file(s), +{sum(f.get('additions', 0) for f in files)} -{sum(f.get('deletions', 0) for f in files)} lines."]
    lines += [f"  {a.ljust(width)}  {b.ljust(12)}  {c}" for a, b, c in rows]
    return "\n".join(lines)


def lint_policy(repo: str) -> tuple[int, str]:
    """`.itemator.toml` in the working tree against the repository's tracked files (policy.lint). Exit 1 when there is
    anything to tidy, so a team can run it in its own CI; 0 when the file is clean or there is no file."""
    try:
        with open(f"{repo}/{POL.FILE}", "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return 0, f"No {POL.FILE} in {repo}: the default rules apply, nothing to check."
    tracked = subprocess.run(["git", "-C", repo, "ls-files", "-z"], capture_output=True)
    if tracked.returncode != 0:
        raise ci.JobError("git ls-files failed: is this a git repository?")
    findings = POL.lint(data, [p for p in tracked.stdout.decode("utf-8", "replace").split("\0") if p])
    return (1, "\n".join(f"- {x}" for x in findings)) if findings else (0, f"{POL.FILE} is clean: every ignore entry has a reason and matches a file.")


def main(argv=None, out=sys.stdout) -> int:
    ap = argparse.ArgumentParser(prog="itemator.local", description=(__doc__ or "").split("\n\n")[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--issue", help="file with the issue text, or - for standard input")
    src.add_argument("--issue-text", help="the issue text itself")
    src.add_argument("--commits", action="store_true", help="use the commit messages from BASE to HEAD as the request (no issue needed)")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", help="commit to diff from (default: merge base with --target)")
    ap.add_argument("--target", default="main", help="branch to take the merge base with when --base is not given")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--map", action="store_true", help="also print every changed file with its lines and why it was or was not listed")
    ap.add_argument("--lint-policy", action="store_true", help="check .itemator.toml (reasons, dead patterns) instead of a diff")
    a = ap.parse_args(argv)
    try:
        if a.lint_policy:
            code, text = lint_policy(a.repo)
            print(text, file=out)
            return code
        if a.issue == "-":
            text = sys.stdin.read()
        elif a.issue:
            with open(a.issue, encoding="utf-8", errors="replace") as f:
                text = f.read()
        else:
            text = a.issue_text or ""
        base = a.base or merge_base(a.repo, a.target, a.head)
        if a.commits:
            text = commit_messages(a.repo, base, a.head)
        files = ci.diff_files(a.repo, base, a.head)
    except (ci.JobError, OSError) as e:
        print(f"itemator.local: {e}", file=sys.stderr)
        return 2
    analysis = X.analyse(text, files)
    print(render(analysis, len(files), bool(text.strip()), "commit messages" if a.commits else "issue text"), file=out)
    if a.map:
        print("\n" + file_map(analysis, files, file_facts(a.repo, base, a.head, files)), file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
