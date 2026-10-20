"""Text that an outsider writes, handed to something that runs or obeys it. Standard library only; no model.

A merge request title, a description, a commit message, a branch name or a label is written by whoever opens the request.
GitLab puts them in CI variables (`CI_MERGE_REQUEST_TITLE`, `CI_COMMIT_MESSAGE`, `CI_COMMIT_REF_NAME`, ...); GitHub Actions pastes
them into a script before the shell runs (`${{ github.event.pull_request.title }}`). The incidents are public: the Nx workflow
(August 2025), the Ultralytics action (December 2024), the Cline triage workflow that put an issue title into an agent's prompt
(2026). This reads only added lines of CI files and shell scripts and names three uses: a GitHub expression of that kind inside a
`run:` or `script:` line (in a workflow or in a composite action file; the text may be any term of the expression, as in `a || b`), one of those variables on the same line as an interpreter that runs text (`eval`, `sh -c`, `python -c`,
`node -e`, `jq`, `sed`, `awk`), and one of them on the same line as an AI command-line tool. A variable inside double quotes in
an ordinary command (`echo "$CI_MERGE_REQUEST_TITLE"`) is not reported: the shell does not run it. A fact about the added line,
not a finding. Information only."""
from __future__ import annotations

import re

from itemator import pipeline as PL
from itemator import shapes as SH
from itemator import fence as FE

MAX_FOUND = 20
SHOWN = 3

# Read at https://gitlab.com/gitlab-org/gitlab/-/blob/master/doc/ci/variables/predefined_variables.md: text a person writes.
GITLAB_VARS = ("CI_COMMIT_MESSAGE", "CI_COMMIT_TITLE", "CI_COMMIT_DESCRIPTION", "CI_COMMIT_AUTHOR", "CI_COMMIT_TAG_MESSAGE",
               "CI_COMMIT_REF_NAME", "CI_COMMIT_BRANCH", "CI_COMMIT_TAG", "CI_MERGE_REQUEST_TITLE", "CI_MERGE_REQUEST_DESCRIPTION",
               "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME", "CI_MERGE_REQUEST_TARGET_BRANCH_NAME", "CI_MERGE_REQUEST_LABELS",
               "CI_MERGE_REQUEST_MILESTONE", "CI_EXTERNAL_PULL_REQUEST_SOURCE_BRANCH_NAME")
_VAR = re.compile(r"\$(?:\{(" + "|".join(GITLAB_VARS) + r")[}:#%/^,-]|(" + "|".join(GITLAB_VARS) + r")\b)")
_EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}")
_STRANGER = re.compile(r"github\.event\.(?:pull_request\.(?:title|body|head\.ref|head\.label|head\.repo\.default_branch)|"
                       r"issue\.(?:title|body)|comment\.body|review\.body|review_comment\.body|discussion\.(?:title|body)|"
                       r"pages\.[\w.\[\]*]*\.page_name|head_commit\.(?:message|author\.(?:email|name))|"
                       r"commits\[[^\]]*\]\.(?:message|author\.(?:email|name))|workflow_run\.(?:head_branch|head_commit\.(?:message|author\.(?:email|name))))|"
                       r"github\.head_ref\b")
_INTERPRETER = re.compile(r"\b(?:eval|(?:ba|z|da|k)?sh\s+-c|python3?\s+-c|node\s+-e|ruby\s+-e|perl\s+-e|jq|sed|awk|Invoke-Expression|iex)\b")
_AGENT = re.compile(r"\b(?:claude|gemini|codex|aider|opencode|cursor-agent|copilot|llm|goose|amp)\b(?:\s|$)", re.I)
_KEY = re.compile(r"^\s*(?:-\s+)?([\w.-]+):(?:\s|$)")
_SCRIPT_KEYS = {"script", "before_script", "after_script", "run", "entrypoint", "command", "args", "prompt"}


def is_target(path: str) -> bool:
    return PL.is_ci_path(path) or path.startswith(".github/workflows/") or path.endswith((".sh", ".bash")) or path.rsplit("/", 1)[-1] in ("action.yml", "action.yaml")


def _pastes_stranger_text(text: str) -> bool:
    return any(_STRANGER.search(m.group(1)) for m in _EXPRESSION.finditer(text))


def _in_single_quotes(line: str, at: int) -> bool:
    """True when position `at` lies inside a single-quoted string of the shell line (no expansion happens there); a single
    quote inside double quotes is an ordinary character."""
    single = double = False
    i = 0
    while i < at:
        c = line[i]
        if c == "\\" and not single:
            i += 2
            continue
        if c == "'" and not double:
            single = not single
        elif c == '"' and not single:
            double = not double
        i += 1
    return single


def _command_like(line: str, is_script: bool) -> bool:
    if is_script:
        return True
    m = _KEY.match(line)
    if m is None:
        return True                        # a list item or a line of a block scalar
    return m.group(1) in _SCRIPT_KEYS      # `script: eval ...` on one line; `variables:` and `rules:` are not commands


def find(files: list[dict]) -> list[dict]:
    """[{path, line, kind, text}] with kind github-expression, interpreter or agent-prompt."""
    found = []
    for f in files:
        path = f.get("filename", "")
        if f.get("status") == "removed" or not f.get("patch") or not is_target(path) or FE._SKIP_PATH.search(path):
            continue
        script = path.endswith((".sh", ".bash"))
        for n, text in SH.added(f["patch"]):
            if text.lstrip().startswith("#"):
                continue
            kind = None
            if _pastes_stranger_text(text) and _command_like(text, script):
                kind = "github-expression"
            else:
                for m in _VAR.finditer(text):
                    if _in_single_quotes(text, m.start()) or not _command_like(text, script):
                        continue
                    if _AGENT.search(text):
                        kind = "agent-prompt"
                    elif _INTERPRETER.search(text):
                        kind = "interpreter"
                    if kind:
                        break
            if kind:
                found.append({"path": path, "line": n, "kind": kind, "text": text.strip()[:80]})
                if len(found) >= MAX_FOUND:
                    return found
    return found


_WHAT = {"github-expression": "pastes text a stranger writes into a script before the shell runs it",
         "interpreter": "hands text a stranger writes to an interpreter that runs it",
         "agent-prompt": "puts text a stranger writes into an AI tool's prompt"}


def sentence(found: list[dict]) -> str:
    parts = [f"`{d['path']}` line {d['line']} {_WHAT[d['kind']]}" for d in found[:SHOWN]]
    more = f" and {len(found) - SHOWN} more" if len(found) > SHOWN else ""
    return "The change adds lines that treat a title, description, commit message or branch name as trusted: " + "; ".join(parts) + more + "."
