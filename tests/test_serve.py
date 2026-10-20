"""itemator/serve.py: the checks over HTTP. The pure function is tested directly; one test starts the real server on a free local port."""
import http.client
import json
import pathlib
import threading
from http.server import ThreadingHTTPServer

from itemator import serve as S

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIFF = ("diff --git a/.github/workflows/a.yml b/.github/workflows/a.yml\n--- a/.github/workflows/a.yml\n+++ b/.github/workflows/a.yml\n"
        "@@ -1,1 +1,2 @@\n a: 1\n+      - run: echo ${{ github.event.issue.title }}\n")


def test_a_diff_with_a_stranger_expression_is_named_and_the_answer_says_it_is_not_a_verdict():
    status, out = S.check(DIFF.encode())
    assert status == 200 and out["files"] == 1 and out["named"] == 1
    assert out["found"][0]["check"] == "untrusted" and out["found"][0]["kind"] == "github-expression" and out["found"][0]["line"] == 2
    assert "not a verdict" in out["note"]


def test_an_ordinary_diff_names_nothing():
    status, out = S.check(b"diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,1 +1,2 @@\n x = 1\n+y = 2\n")
    assert status == 200 and out["named"] == 0 and out["found"] == []


def test_empty_text_and_text_that_is_not_a_diff_are_refused_and_the_cap_is_exact():
    assert S.check(b"  \n")[0] == 400 and S.check(b"hello")[0] == 400
    assert S.check(b"x" * S.MAX_BODY)[0] == 400                        # at the cap: read, but not a diff
    assert S.check(b"x" * (S.MAX_BODY + 1))[0] == 413


def _serve():
    server = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _call(server, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    r = conn.getresponse()
    return r.status, r.getheader("Cache-Control"), json.loads(r.read() or b"{}")


def test_the_server_answers_only_get_root_and_post_check_and_stores_nothing():
    server = _serve()
    try:
        status, cache, out = _call(server, "POST", "/check", DIFF.encode(), {"Content-Length": str(len(DIFF))})
        assert status == 200 and out["named"] == 1 and cache == "no-store"
        assert _call(server, "GET", "/")[2]["stores"] == "nothing"
        assert _call(server, "GET", "/check")[0] == 404 and _call(server, "POST", "/other", b"x", {"Content-Length": "1"})[0] == 404
        big = S.MAX_BODY + 1
        assert _call(server, "POST", "/check", b"x", {"Content-Length": str(big)})[0] == 413      # refused before the body is read
        assert _call(server, "POST", "/check", None, {})[0] == 400                                # an empty body is not a diff
        raw = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        raw.putrequest("POST", "/check")
        raw.endheaders()
        assert raw.getresponse().status == 411                                                    # no Content-Length at all
    finally:
        server.shutdown()


def test_the_request_is_not_logged(capsys):
    assert S.Handler.log_message(None, "%s", "POST /check") is None
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_all_three_checks_are_run():
    moving = b"diff --git a/.gitlab-ci.yml b/.gitlab-ci.yml\n--- a/.gitlab-ci.yml\n+++ b/.gitlab-ci.yml\n@@ -1,1 +1,2 @@\n a: 1\n+  image: python:latest\n"
    got = S.check(moving)[1]["found"]
    assert [(d["check"], d["kind"]) for d in got] == [("moving", "image-latest")]
    assert [name for name, _ in S.CHECKS] == ["shapes", "untrusted", "moving"]


def test_the_image_copies_only_the_package_and_runs_as_a_non_root_user():
    docker = (ROOT / "Dockerfile").read_text()
    assert "COPY itemator/" in docker and "COPY . " not in docker and "USER itemator" in docker and "itemator.serve" in docker
    ignore = (ROOT / ".dockerignore").read_text().split()
    assert ignore[0] == "*" and "!itemator/" in ignore


def test_the_cloud_run_job_is_manual_needs_its_variables_keeps_no_key_and_caps_the_service():
    import yaml
    job = yaml.safe_load((ROOT / ".gitlab-ci.yml").read_text())["deploy-cloud-run"]
    rule = job["rules"][0]
    assert rule["when"] == "manual" and all(v in rule["if"] for v in ("GCP_PROJECT_ID", "GCP_WIF_AUDIENCE", "GCP_SERVICE_ACCOUNT"))
    assert "GCP_ID_TOKEN" in job["id_tokens"] and job["id_tokens"]["GCP_ID_TOKEN"]["aud"] == "$GCP_WIF_AUDIENCE"
    run = "\n".join(job["script"])
    assert "--max-instances=1" in run and "--timeout=10" in run and "--concurrency=20" in run and "--allow-unauthenticated" in run
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in run and "service-account-key" not in run and "credentials.json" not in run
    assert "rm -f" in "\n".join(job["after_script"]) and job["environment"]["name"] == "google-cloud"
    assert (ROOT / "examples" / "cloud-run-sample.diff").exists() and S.check((ROOT / "examples" / "cloud-run-sample.diff").read_bytes())[1]["named"] == 1
