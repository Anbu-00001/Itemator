"""Runs one of our registered evaluation jobs on a Hugging Face Space (2 CPUs, 16 GB), next to the dataset, so the laptop
is not used. Stdlib only. /health is public and harmless; everything else needs the X-Token header (Space secret
RUNNER_TOKEN). One job at a time; jobs come from a fixed list, never from the request."""
import hmac, http.server, json, os, pathlib, subprocess, sys, threading, time, urllib.parse, urllib.request

APP = pathlib.Path(__file__).resolve().parent.parent
DATA = pathlib.Path(os.environ.get("RUNNER_DATA", "/tmp/runner-data"))
TOKEN = os.environ.get("RUNNER_TOKEN", "")
COMMIT_DETAILS_URL = "https://huggingface.co/datasets/hao-li/AIDev/resolve/main/pr_commit_details.parquet"
STATE = {"job": None, "state": "idle", "started": None, "ended": None, "note": "", "log_tail": ""}
LOCK = threading.Lock()


def authorized(given, token):
    """A request is allowed only when a token is set and the header carries exactly it."""
    return bool(token) and bool(given) and hmac.compare_digest(str(given), str(token))


def job_command(name, data_dir):
    """argv and result file of a known job, or None."""
    if name == "leg2":
        return ([sys.executable, "eval/aidev_revert.py", "--score", "--commit-details", str(pathlib.Path(data_dir) / "pr_commit_details.parquet")],
                "results/aidev_revert_v6.json")
    if name == "population":
        return ([sys.executable, "-u", "eval/aidev_population.py", "--commit-details", str(pathlib.Path(data_dir) / "pr_commit_details.parquet")],
                "results/aidev_population_v6.json")
    if name == "weight":
        return ([sys.executable, "-u", "eval/aidev_weight.py", "--commit-details", str(pathlib.Path(data_dir) / "pr_commit_details.parquet")],
                "results/aidev_weight_v1.json")
    if name == "check":
        return ([sys.executable, "eval/hf_check.py", str(pathlib.Path(data_dir) / "pr_commit_details.parquet")], "results/hf_check.json")
    return None


def download(url, dest, note):
    dest = pathlib.Path(dest)
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=300) as r, open(tmp, "wb") as out:
        done = 0
        while chunk := r.read(1 << 22):
            out.write(chunk)
            done += len(chunk)
            note(f"downloaded {done // 1_000_000} MB")
    tmp.rename(dest)


def run_job(name):
    cmd, result_file = job_command(name, DATA)
    try:
        def note(t):
            STATE["note"] = t
        download(COMMIT_DETAILS_URL, DATA / "pr_commit_details.parquet", note)
        STATE["note"] = "scoring"
        p = subprocess.Popen(cmd, cwd=APP, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        tail = []
        for line in p.stdout:
            tail = (tail + [line.rstrip()])[-30:]
            STATE["note"], STATE["log_tail"] = line.strip()[:120], "\n".join(tail)[-3000:]
        STATE["state"] = "done" if p.wait() == 0 and (APP / result_file).exists() else "failed"
    except Exception as e:
        STATE["state"], STATE["log_tail"] = "failed", f"{type(e).__name__}: {e}"[:500]
    STATE["ended"] = time.time()


class H(http.server.BaseHTTPRequestHandler):
    def send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        if authorized(self.headers.get("X-Token"), TOKEN):
            return True
        self.send(403, {"error": "token required"})
        return False

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":
            return self.send(200, {"ok": True, "state": STATE["state"], "job": STATE["job"]})
        if not self.allowed():
            return
        if path == "/status":
            return self.send(200, dict(STATE, elapsed_s=round((STATE["ended"] or time.time()) - STATE["started"], 1) if STATE["started"] else None))
        if path == "/result":
            cmd = job_command(STATE["job"] or "", DATA)
            f = APP / cmd[1] if cmd else None
            if STATE["state"] == "done" and f and f.exists():
                return self.send(200, json.loads(f.read_text()))
            return self.send(404, {"error": "no finished result", "state": STATE["state"]})
        self.send(404, {"error": "unknown path"})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if not self.allowed():
            return
        if u.path != "/run":
            return self.send(404, {"error": "unknown path"})
        name = urllib.parse.parse_qs(u.query).get("job", [""])[0]
        if job_command(name, DATA) is None:
            return self.send(400, {"error": "unknown job"})
        with LOCK:
            if STATE["state"] == "running":
                return self.send(409, {"error": "a job is running", "job": STATE["job"]})
            STATE.update(job=name, state="running", started=time.time(), ended=None, note="starting", log_tail="")
        threading.Thread(target=run_job, args=(name,), daemon=True).start()
        self.send(202, {"started": name})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "7860"))), H).serve_forever()
