"""The one sentence the card adds for what two checks that need no request found: modified Python files that changed only
in layout, comments, docstrings or plain-function order (itemator/neutral.py), and binary files the opener read
(itemator/unwrap.py). It tells a reviewer what the rules looked at, not that anything is fine: the extras and the
card's state do not depend on it. Standard library only; no model."""
from __future__ import annotations

from itemator import cochange as CC
from itemator import fence as FE
from itemator import moving as MV
from itemator import pipeline as PL
from itemator import refs as RF
from itemator import scanners as SC
from itemator import shapes as SP
from itemator import untrusted as UT
from itemator import record as RC
from itemator import reland as RL
from itemator import revert as RV

MAX_LINE = 1400           # characters of the card line before the rest is left to itemator.json
SHOWN = 3        # names per list; the rest are counted


def _names(paths: list[str]) -> str:
    shown = ", ".join(f"`{p}`" for p in paths[:SHOWN])
    return shown + (f" and {len(paths) - SHOWN} more" if len(paths) > SHOWN else "")


def _fence_part(fenced: list[dict]) -> str:
    seen, items = set(), []
    for d in fenced:
        key = (d["path"], d["commit"])
        if key not in seen:
            seen.add(key)
            items.append(d)
    shown = "; ".join(f"`{d['path']}` ({d['lines']} {'line' if d['lines'] == 1 else 'lines'} added by `{d['commit']}`, \"{d['subject']}\")"
                      for d in items[:SHOWN])
    more = f" and {len(items) - SHOWN} more" if len(items) > SHOWN else ""
    return f"This change deletes lines that a commit whose subject says it fixes something had added: {shown}{more}."


def _reland_part(relanded: list[dict]) -> str:
    shown = "; ".join(f"`{d['path']}` ({d['lines']} {'line' if d['lines'] == 1 else 'lines'}, removed by `{d['commit']}`, \"{d['subject']}\", {d['date']})"
                      for d in relanded[:SHOWN])
    more = f" and {len(relanded) - SHOWN} more" if len(relanded) > SHOWN else ""
    return f"This change adds back lines that a revert removed earlier: {shown}{more}."


def sentence(neutral: list[str], opened: list[tuple[str, str]], strangers: list[str] = (), fenced: list[dict] = (),
             pipeline: dict | None = None, relanded: list[dict] = (), cites: list[dict] = (),
             revert: dict | None = None, moving: list[dict] = (), record: dict | None = None, copy: dict | None = None, shapes: list[dict] = (), untrusted: list[dict] = (), scanners: dict | None = None, dotnet: str | None = None) -> str | None:
    """`neutral`: paths the layout check proved; `opened`: (path, what the opener read); `strangers`: modified files with
    history that never changed in a commit with any other changed file; `fenced`: itemator.fence.find()["fenced"];
    `pipeline`: itemator.pipeline.find()'s result; `relanded`: itemator.reland.find()["relanded"]; `cites`: itemator.refs.find(); `revert`: itemator.revert.find(); `moving`: itemator.moving.find(); `record`: itemator.record.find(); `copy`: itemator.revert.find(copy=True); `shapes`: itemator.shapes.find(); `untrusted`: itemator.untrusted.find(); `scanners`: itemator.scanners.find(). None when all fourteen are empty."""
    parts = []
    if neutral:
        n = len(neutral)
        parts.append(f"{n} Python {'file' if n == 1 else 'files'} changed only in layout, comments, docstrings or the order "
                     f"of plain functions: {_names(neutral)}.")
    if strangers:
        n = len(strangers)
        parts.append(f"In the repository's history {_names(list(strangers))} {'has' if n == 1 else 'have'} never changed in the same "
                     f"commit as {'any other file' if n == 1 else 'any of the other files'} changed here.")
    if fenced:
        parts.append(_fence_part(fenced))
    if relanded:
        parts.append(_reland_part(list(relanded)))
    if cites:
        parts.append(RF.sentence(list(cites)))
    if revert:
        parts.append(RV.sentence(revert))
    if copy:
        parts.append(RV.sentence(copy))
    if scanners:
        parts.append(SC.sentence(scanners))
    if untrusted:
        parts.append(UT.sentence(list(untrusted)))
    if shapes:
        parts.append(SP.sentence(list(shapes)))
    if moving:
        parts.append(MV.sentence(list(moving)))
    if record:
        parts.append(RC.sentence(record))
    if dotnet:
        parts.append(dotnet)
    if pipeline:
        parts.append(PL.sentence(pipeline))
    for path, line in opened[:SHOWN]:
        parts.append(f"Opened `{path}`: {line}.")
    if len(opened) > SHOWN:
        more = len(opened) - SHOWN
        parts.append(f"{more} more binary {'file' if more == 1 else 'files'} opened.")
    if not parts:
        return None
    head, kept, used = "Also checked, with no model: ", [], 0
    for part in parts:
        if kept and used + len(part) + 1 > MAX_LINE:
            break
        kept.append(part)
        used += len(part) + 1
    if len(kept) < len(parts):
        left = len(parts) - len(kept)
        kept.append(f"{left} more {'result is' if left == 1 else 'results are'} in `checked` in itemator.json.")
    return head + " ".join(kept)


def history_checks(repo: str, base: str, files: list[dict], listed: set, warnings: list) -> tuple[dict[str, str], dict]:
    """The two checks that read the repository's history, for the card and for the trace: ({path: label} from
    itemator.cochange, empty unless three to MAX_FILES files were modified) and itemator.fence.find()'s result. A check that
    breaks adds a warning and gives its empty answer."""
    modified = [f["filename"] for f in files if f.get("status") == "modified"]
    labels: dict[str, str] = {}
    if 3 <= len(modified) <= CC.MAX_FILES:
        try:
            labels = CC.strangers({p: CC.history(repo, base, p) for p in modified})
        except Exception as e:            # noqa: BLE001 -- a check that cannot read the history says nothing
            warnings.append(f"no history check: {type(e).__name__}")
    fence = {"fenced": [], "runs_read": 0, "capped": False}
    try:
        fence = FE.find(repo, base, files, listed)
    except Exception as e:                # noqa: BLE001
        warnings.append(f"no fence check: {type(e).__name__}")
    return labels, fence


def reland_check(repo: str, base: str, files: list[dict], warnings: list) -> dict:
    """itemator.reland.find()'s result; a check that breaks adds a warning and gives its empty answer."""
    try:
        return RL.find(repo, base, files)
    except Exception as e:                # noqa: BLE001
        warnings.append(f"no reland check: {type(e).__name__}")
        return {"relanded": [], "runs_read": 0, "capped": False}
