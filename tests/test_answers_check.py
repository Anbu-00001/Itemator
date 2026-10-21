"""The answer page's button (web/answers_check.js) must hash exactly as itemator/answerlog.py does, run under node."""
import json
import shutil
import subprocess

import pytest

from itemator import answerlog as L

ODD = ['quote " and \\ back', "tab\tline\nfeed\r\b\f", "\x00\x1f\x7f", "café naïve", "emoji 😀 and 中文", "/slash/ <b>&amp;</b>"]

RUN = """
const C = require(process.argv[1]);
const crypto = require("crypto");
const digest = async (t) => crypto.createHash("sha256").update(t, "utf8").digest("hex");
const data = JSON.parse(process.argv[2]);
(async () => {
  const out = { canonical: data.values.map(C.canonical), verdicts: [] };
  for (const entries of data.chains) out.verdicts.push(await C.verify(entries, digest));
  process.stdout.write(JSON.stringify(out));
})();
"""


def entries():
    rows = []
    for k, text in enumerate(ODD):
        rows.append({"iid": 100 + k, "note": 9000 + k, "at": f"2026-10-2{k}T10:00:00Z", "commit": "c" * 40,
                     "items": [{"name": text, "decision": "kept", "who": "alice", "ref": None}], "body_sha256": "d" * 64,
                     "url": f"https://gitlab.example/g/p/-/merge_requests/{100 + k}#note_{9000 + k}"})
    return L.chain(rows)


def node(values, chains):
    payload = json.dumps({"values": values, "chains": chains})
    got = subprocess.run(["node", "-e", RUN, str(L.CHECK_JS), payload], capture_output=True, text=True, check=True)
    return json.loads(got.stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_the_browser_writes_each_entry_as_python_does():
    values = [{k: v for k, v in e.items() if k not in ("prev", "hash")} for e in entries()] + [{"b": [1, True, None], "a": {"z": 0, "y": False}}]
    assert node(values, [])["canonical"] == [json.dumps(v, sort_keys=True, separators=(",", ":")) for v in values]


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_the_browser_finds_the_same_break_as_python():
    good = entries()
    edited = [dict(e) for e in good]
    edited[3] = dict(edited[3], items=[dict(edited[3]["items"][0], decision="removed")])
    relinked = L.chain([{k: v for k, v in e.items() if k not in ("prev", "hash")} for e in good[:2]]) + good[3:]
    head_only = [dict(e) for e in good]
    head_only[-1] = dict(head_only[-1], hash="0" * 64)
    wrong_link = [dict(e) for e in good]
    wrong_link[1] = dict(wrong_link[1], prev="f" * 64)
    chains = [good, edited, relinked, head_only, wrong_link, []]
    assert node([], chains)["verdicts"] == [L.verify(c) for c in chains] == [None, 3, 2, len(good) - 1, 1, None]


def test_the_page_carries_the_button_and_lets_only_its_own_script_run():
    log = {"entries": entries(), "started": "s", "head": entries()[-1]["hash"], "note": "", "changed_after_recorded": []}
    html = L.page(log)
    assert f'data-head="{log["head"]}"' in html and '<script src="check.js"></script>' in html
    assert "script-src 'self'; connect-src 'self';" in html and "unsafe-inline'; script" in html
