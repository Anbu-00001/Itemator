"""tools/smoke_check.py: the post-deploy check (stage Monitor)."""
import importlib.util
import pathlib

SPEC = importlib.util.spec_from_file_location("smoke_check", pathlib.Path(__file__).resolve().parent.parent / "tools" / "smoke_check.py")
S = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S)


def script(*answers):
    it = iter(answers)
    return lambda url: next(it)


def test_a_page_that_answers_200_passes_at_once():
    slept = []
    assert S.main(["https://x/"], 3, 5, sleep=slept.append, get=script(200)) == 0 and slept == []


def test_a_page_that_comes_up_late_passes_after_waiting():
    slept = []
    assert S.main(["https://x/"], 4, 7, sleep=slept.append, get=script(404, 0, 200)) == 0 and slept == [7, 7]


def test_a_page_that_never_answers_fails_and_is_named(capsys):
    slept = []
    assert S.main(["https://x/"], 3, 1, sleep=slept.append, get=script(404, 404, 404)) == 1
    assert "NOT SERVED: https://x/" in capsys.readouterr().err and slept == [1, 1]


def test_one_bad_page_fails_the_run_but_the_others_are_still_checked(capsys):
    assert S.main(["https://a/", "https://b/", "https://c/"], 1, 0, sleep=lambda s: None, get=script(200, 500, 200)) == 1
    out = capsys.readouterr()
    assert "ok https://a/" in out.out and "ok https://c/" in out.out and "NOT SERVED: https://b/" in out.err


def test_fetch_reports_the_status_of_a_refusal_and_zero_for_no_answer(monkeypatch):
    import urllib.error
    import urllib.request

    def refuse(*a, **k):
        raise urllib.error.HTTPError("u", 503, "busy", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    assert S.fetch("https://x/") == 503
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    assert S.fetch("https://x/") == 0
