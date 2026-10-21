"""itemator/powers.py: code that can do something new, which the same file did not do before."""
import subprocess

import pytest

from itemator import checked as C
from itemator import powers as P


def f(path, *added, status="modified", removed=(), context=()):
    body = "".join(f" {c}\n" for c in context) + "".join(f"-{r}\n" for r in removed) + "".join(f"+{a}\n" for a in added)
    return {"filename": path, "status": status, "patch": f"@@ -1,{len(context) + len(removed)} +1,{len(context) + len(added)} @@\n{body}"}


def powers(*files, before=None):
    return [(d["path"], d["power"]) for d in P.find(list(files), before)]


@pytest.mark.parametrize("line,power", [
    ("r = requests.post(url, json=data)", "network"), ("with urllib.request.urlopen(u) as r:", "network"),
    ("s = socket.create_connection((h, p))", "network"), ("const r = await fetch(url);", "network"),
    ("axios.get(u)", "network"), ("resp, err := http.Get(u)", "network"), ("let c = reqwest::Client::new();", "network"),
    ("subprocess.run(['git', 'push'])", "process"), ("os.system('rm -rf build')", "process"),
    ("const { execSync } = require('child_process');", "process"), ("cmd := exec.Command(\"sh\", \"-c\", s)", "process"),
    ("Command::new(\"sh\").spawn()", "process"), ("new ProcessBuilder(args).start();", "process"),
    ("payload = dict(os.environ)", "environment"), ("env = os.environ.copy()", "environment"),
    ("body: JSON.stringify(process.env)", "environment"), ("const all = { ...process.env };", "environment"),
    ("key = open(os.path.expanduser('~/.ssh/id_rsa')).read()", "environment"), ("for (k, v) in env::vars() {", "environment"),
    ("eval(code)", "dynamic"), ("exec(compile(src, 'x', 'exec'))", "dynamic"), ("obj = pickle.loads(blob)", "dynamic"),
    ("m = importlib.import_module(name)", "dynamic"), ("const g = new Function(src);", "dynamic"),
])
def test_each_power_is_named(line, power):
    assert powers(f("src/app/mod.py", line)) == [("src/app/mod.py", power)]


@pytest.mark.parametrize("line", [
    "url = os.environ.get('API_URL')", "port = process.env.PORT", "x = literal_eval(s)", "self.exec(q)", "regex.exec(s)",
    "# requests.post(u)", "// fetch(u)", "def fetch_rows(self):", "name = 'subprocess'", "-- eval(x)",
])
def test_ordinary_lines_are_not(line):
    assert powers(f("src/app/mod.py", line)) == []


@pytest.mark.parametrize("path", ["tests/test_a.py", "Tests/Unit/a.ts", "src/a.test.ts", "src/a_spec.rb", "docs/a.py",
                                  "dist/a.js", "pkg/.tshy-build/a.js", "node_modules/x/a.js", "README.md", "a.json", "e2e/a.ts"])
def test_tests_docs_build_output_and_non_code_are_not_read(path):
    assert powers(f(path, "requests.post(u)")) == []


def test_a_power_the_file_already_had_is_not_new():
    assert powers(f("src/a.py", "requests.get(u)"), before={"src/a.py": "import requests\nrequests.post(x)\n"}) == []
    assert powers(f("src/a.py", "requests.get(u)"), before={"src/a.py": "x = 1\n"}) == [("src/a.py", "network")]
    assert powers(f("src/a.py", "requests.get(u)", context=("requests.post(x)",))) == []          # no base text: the patch
    assert powers(f("src/a.py", "requests.get(u)", context=("requests.post(x)",)), before={"src/b.py": ""}) == []
    assert powers(f("src/a.py", "requests.get(u)", removed=("requests.post(x)",))) == []
    assert powers(f("src/a.py", "requests.get(u)", status="added", context=("requests.post(x)",))) == [("src/a.py", "network")]
    assert powers(f("src/a.py", "requests.get(u)", status="removed")) == [] and powers({"filename": "src/a.py"}) == []


def test_one_line_per_power_per_file_with_its_number_and_cut_text():
    got = P.find([f("src/a.py", "x = 1", "requests.get(u)", "requests.post(u)", "subprocess.run(['" + "a" * 200 + "'])")])
    assert [(d["power"], d["line"]) for d in got] == [("network", 2), ("process", 4)]
    assert len(got[1]["text"]) == P.MAX_TEXT


def test_read_before(tmp_path):
    r = str(tmp_path)
    subprocess.run(["git", "init", "-q", r], check=True)
    (tmp_path / "a.py").write_text("import requests\n")
    (tmp_path / "c.py").write_text("old\n")
    subprocess.run(["git", "-C", r, "add", "."], check=True)
    subprocess.run(["git", "-C", r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "a"], check=True)
    base = subprocess.run(["git", "-C", r, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    files = [f("a.py", "x"), f("b.py", "y", status="added"), f("gone.py", "z"), f("c.py", "w", status="removed"), f("README.md", "q"),
             {**f("new.py", "v"), "previous_filename": "a.py"}]
    assert P.read_before(r, base, files) == {"a.py": "import requests\n", "b.py": "", "new.py": "import requests\n"}


def test_the_sentence_names_three_and_counts_the_rest_and_sits_on_the_card():
    found = [{"path": f"src/m{i}.py", "power": "network", "line": i, "text": "fetch(u)"} for i in range(5)]
    s = P.sentence(found)
    assert s.startswith("Code that can do something new") and s.count("now reaches the network") == 3 and s.endswith("; and 2 more.")
    assert P.sentence(found[:1]).endswith("(`fetch(u)`).")
    line = C.sentence([], [], powers=found[:1])
    assert line.startswith("Also checked, with no model: Code that can do something new")
