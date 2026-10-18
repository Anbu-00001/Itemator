"""itemator/mapview.py: the page that draws trace.json, with the data inlined."""
import json

from itemator import mapview as M

TRACE = {"schema": 1, "source": {"base_sha": "a" * 40, "head_sha": "b" * 40, "rules_version": 6, "input_sha256": "c" * 64},
         "files": [{"path": "</script><img src=x onerror=alert(1)>.py", "status": "modified", "additions": 1, "deletions": 0,
                    "route": [], "landing": "ordinary"}], "totals": {"listed": 0, "opened": 0, "neutral": 0, "ordinary": 1}}


def write(tmp_path, name="t.json", data=None):
    f = tmp_path / name
    f.write_text(json.dumps(TRACE if data is None else data))
    return str(f)


def inlined(html):
    start = html.index('<script id="traces" type="application/json">') + len('<script id="traces" type="application/json">')
    return json.loads(html[start:html.index("</script>", start)])


def test_a_hostile_file_name_cannot_close_the_script_tag_and_survives_the_round_trip(tmp_path):
    out = tmp_path / "out"
    assert M.main(["--out", str(out), write(tmp_path)]) == 0
    html = (out / "index.html").read_text()
    assert html.count("</script>") == 2                                              # the data tag and the code tag only
    assert "<img src=x" not in html
    assert inlined(html)[0]["trace"]["files"][0]["path"] == TRACE["files"][0]["path"]


def test_labels_staged_flags_and_order(tmp_path):
    a, b = write(tmp_path, "a.json"), write(tmp_path, "b.json")
    out = tmp_path / "out"
    assert M.main(["--out", str(out), "--label", "First", "--label", "Second", "--staged", b, a, b]) == 0
    d = inlined((out / "index.html").read_text())
    assert [(e["label"], e["kind"]) for e in d] == [("First", "real"), ("Second", "staged")]
    assert M.main(["--out", str(out), a]) == 0 and inlined((out / "index.html").read_text())[0]["label"] == "a"


def test_a_missing_file_is_an_error_unless_skipped_and_labels_stay_with_their_file(tmp_path, capsys):
    a = write(tmp_path, "a.json")
    gone = str(tmp_path / "gone.json")
    out = tmp_path / "out"
    assert M.main(["--out", str(out), gone, a]) == 2 and "gone.json" in capsys.readouterr().err
    assert M.main(["--out", str(out), "--skip-missing", "--label", "Latest", "--label", "Staged", gone, a]) == 0
    assert [e["label"] for e in inlined((out / "index.html").read_text())] == ["Staged"]


def test_an_unknown_schema_is_refused(tmp_path, capsys):
    assert M.main(["--out", str(tmp_path / "o"), write(tmp_path, "x.json", {**TRACE, "schema": 3})]) == 2
    assert "schema 3" in capsys.readouterr().err
    assert M.main(["--out", str(tmp_path / "o2"), write(tmp_path, "y.json", {**TRACE, "schema": 2})]) == 0      # the current schema, and 1 above, are read


def test_the_data_tag_holds_no_angle_bracket_or_ampersand(tmp_path):
    odd = {**TRACE, "files": [{**TRACE["files"][0], "path": "a&b>c<d.py"}]}
    out = tmp_path / "out"
    assert M.main(["--out", str(out), write(tmp_path, "o.json", odd)]) == 0
    html = (out / "index.html").read_text()
    tag = '<script id="traces" type="application/json">'
    raw = html[html.index(tag) + len(tag):html.index("</script>", html.index(tag))]
    assert not set("<>&") & set(raw) and inlined(html)[0]["trace"]["files"][0]["path"] == "a&b>c<d.py"


def test_the_page_carries_the_reading_rule_and_no_network_use():
    html = M.TEMPLATE.read_text()
    assert "It is not a statement that the file is fine" in html
    assert "fetch(" not in html and "XMLHttpRequest" not in html and "http://" not in html.replace("http://www.w3.org/2000/svg", "")
    assert "prefers-reduced-motion" in html and 'id="play"' in html and 'id="step"' in html
