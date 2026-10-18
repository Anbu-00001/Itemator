"""Draw trace.json files as one static page: `python -m itemator.mapview --out public/map TRACE.json [...]`.

Each trace (itemator/trace.py) becomes one choice in the page web/map.html: every changed file moves through the checks
into one of the bins, with a table of what each check said below. The data is inlined, so the page needs no network,
works from a file, and can be screen-recorded. A trace's label is its file name unless `--label` is given; `--staged`
marks the page's text "staged for this demonstration, not a real merge request"."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

TEMPLATE = pathlib.Path(__file__).resolve().parent.parent / "web" / "map.html"


def safe_json(data) -> str:
    """JSON for inside a <script> tag: no sequence in a file name can close the tag or open a comment."""
    return json.dumps(data, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def page(entries: list[dict]) -> str:
    """`entries`: [{label, kind ("staged" or "real"), trace}]."""
    return TEMPLATE.read_text(encoding="utf-8").replace("/*TRACES*/", safe_json(entries), 1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="itemator.mapview", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("traces", nargs="+")
    ap.add_argument("--out", default="public/map")
    ap.add_argument("--label", action="append", default=[], help="a label per trace, in order")
    ap.add_argument("--staged", action="append", default=[], help="file names of traces that were staged, not real")
    ap.add_argument("--skip-missing", action="store_true", help="leave out a trace file that does not exist (a best-effort run that failed)")
    a = ap.parse_args(argv)
    entries = []
    for i, name in enumerate(a.traces):
        if a.skip_missing and not pathlib.Path(name).exists():
            continue
        try:
            trace = json.loads(pathlib.Path(name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"itemator.mapview: {name}: {e}", file=sys.stderr)
            return 2
        if trace.get("schema") not in (1, 2):
            print(f"itemator.mapview: {name}: schema {trace.get('schema')!r}, expected 1 or 2", file=sys.stderr)
            return 2
        entries.append({"label": a.label[i] if i < len(a.label) else pathlib.Path(name).stem,
                        "kind": "staged" if name in a.staged else "real", "trace": trace})
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page(entries), encoding="utf-8")
    print(f"wrote {out / 'index.html'} ({len(entries)} trace(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
