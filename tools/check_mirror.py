"""Check that the GitHub copy of this repo holds exactly the files of the GitLab commit it names.

Each GitHub commit is one squash of GitLab main and ends with `GitLab-commit: <sha>`. This clones both public repos
without file contents (trees only), reads that line, and compares the GitHub tree id with the tree id of that GitLab
commit. Equal ids mean every file is byte for byte the same; if either host's copy were changed, they would differ.

usage: python3 tools/check_mirror.py"""
from __future__ import annotations

import re, subprocess, sys, tempfile

GITLAB = "https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/39194174/showcase.git"
GITHUB = "https://github.com/Anbu-00001/Itemator.git"
TRAILER = re.compile(r"^GitLab-commit: ([0-9a-f]{40})$", re.M)


def gitlab_commit(message: str) -> str | None:
    found = TRAILER.findall(message)
    return found[-1] if found else None


def verdict(github_tree: str, gitlab_tree: str, sha: str) -> tuple[int, str]:
    if github_tree == gitlab_tree:
        return 0, f"same files: GitHub main = GitLab {sha[:8]} (tree {github_tree})"
    return 1, f"DIFFERENT: GitHub main tree {github_tree}, GitLab {sha[:8]} tree {gitlab_tree}"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        git("clone", "-q", "--bare", "--filter=blob:none", "--single-branch", "--branch", "main", GITHUB, f"{d}/gh")
        sha = gitlab_commit(git("-C", f"{d}/gh", "log", "-1", "--format=%B"))
        if not sha:
            print("the GitHub commit names no GitLab commit")
            return 2
        git("clone", "-q", "--bare", "--filter=blob:none", "--single-branch", "--branch", "main", GITLAB, f"{d}/gl")
        code, line = verdict(git("-C", f"{d}/gh", "rev-parse", "HEAD^{tree}"),
                             git("-C", f"{d}/gl", "rev-parse", f"{sha}^{{tree}}"), sha)
        ahead = git("-C", f"{d}/gl", "rev-list", "--count", f"{sha}..HEAD")
    print(line)
    if ahead != "0":
        print(f"GitLab main has {ahead} newer commits; the next mirror run copies them")
    return code


if __name__ == "__main__":
    sys.exit(main())
