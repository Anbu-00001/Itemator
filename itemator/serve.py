"""The added-line checks over HTTP: POST a git diff to /check, get back what moving, shapes and untrusted name. `python -m itemator.serve`.

It is the same code the CI job runs, with no model. Nothing is stored or logged from the request body; the body is capped, the read
times out, and only POST /check and GET / exist. It is meant to run on Cloud Run (the port comes from $PORT) behind max-instances 1.
Standard library only."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from itemator import diffreader as DR
from itemator import moving as MV
from itemator import shapes as SH
from itemator import untrusted as UT

MAX_BODY = 200_000
TIMEOUT_S = 10
CHECKS = (("shapes", SH), ("untrusted", UT), ("moving", MV))
USAGE = {"what": "Itemator's added-line checks, no model.", "use": "POST a git diff (text/plain) to /check.", "max_body_bytes": MAX_BODY,
         "stores": "nothing", "source": "https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/39194174/showcase"}


def check(body: bytes) -> tuple[int, dict]:
    """(status, answer) for one request body. Pure: no network, no files."""
    if not body.strip():
        return 400, {"error": "send a git diff in the request body"}
    if len(body) > MAX_BODY:
        return 413, {"error": f"the diff is larger than {MAX_BODY} bytes"}
    files = DR.files_of(body.decode("utf-8", "replace"))
    if not files:
        return 400, {"error": "that does not look like a git diff (it should start with a line like 'diff --git a/x b/x')"}
    found = []
    for name, mod in CHECKS:
        for d in mod.find(files):
            found.append({"check": name, **{k: d[k] for k in ("kind", "path", "line", "text") if k in d}})
    return 200, {"files": len(files), "named": len(found), "found": found,
                 "note": "A fact about the added lines, not a verdict. Nothing named does not mean the change is fine."}


class Handler(BaseHTTPRequestHandler):
    timeout = TIMEOUT_S
    server_version = "itemator"
    sys_version = ""

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:                                         # noqa: N802 -- the name http.server calls
        self._send(200, USAGE) if self.path == "/" else self._send(404, {"error": "not found"})

    def do_POST(self) -> None:                                        # noqa: N802
        if self.path != "/check":
            return self._send(404, {"error": "not found"})
        try:
            size = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._send(411, {"error": "send a Content-Length"})
        if size > MAX_BODY:
            return self._send(413, {"error": f"the diff is larger than {MAX_BODY} bytes"})
        status, payload = check(self.rfile.read(size))
        self._send(status, payload)

    def log_message(self, *_args) -> None:                            # the request line and body are not logged
        return


def main() -> int:
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()   # noqa: S104 -- a container listens on all interfaces
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
