"""Build a small staged change in a temporary git repository and write its trace: `python examples/make_example.py trace.json`.

The change is made up for this demonstration (an "agent" asked to change one greeting also tidies a file, adds a
dependency and an image, hides a program inside a .pdf name, edits the CI file and a README). It is not a real merge
request. The trace is what `python -m itemator.trace` writes for it, so anyone can run this and get the same file."""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import trace as T  # noqa: E402

REQUEST = "Greet the user by name in greeting.py instead of printing Hello."


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=demo@example.invalid", "-c", "user.name=demo", "-c", "commit.gpgsign=false", *args],
                   check=True, capture_output=True)


def build(repo: pathlib.Path) -> None:
    git(repo, "init", "-q", "-b", "main")
    files = {"greeting.py": "def greet():\n    print('Hello')\n", "tidy.py": "X=1\ndef f( a ):\n  return a\n",
             "utils.py": "def add(a, b):\n    return a + b\n", "README.md": "# demo\n", ".github/workflows/ci.yml": "on: push\n"}
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    (repo / "parse.py").write_text("def parse(text):\n    return text.split(',')\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    # history the history checks read: utils.py only ever changes alone; parse.py had a guard added by a bug fix
    (repo / "utils.py").write_text("def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n")
    git(repo, "commit", "-qam", "Add sub")
    (repo / "utils.py").write_text("def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n\n\ndef neg(a):\n    return -a\n")
    git(repo, "commit", "-qam", "Add neg")
    (repo / "parse.py").write_text("def parse(text):\n    if text is None:\n        return []\n    return text.split(',')\n")
    (repo / "greeting.py").write_text("def greet():\n    print('Hello')\n\n")
    git(repo, "commit", "-qam", "Fix crash when text is None in parse")
    git(repo, "checkout", "-qb", "agent")
    (repo / "greeting.py").write_text("def greet(name):\n    print(f'Hello, {name}')\n")
    (repo / "tidy.py").write_text("X = 1\n\n\ndef f(a):\n    return a  # unchanged behaviour\n")
    (repo / "utils.py").write_text("def add(a, b):\n    return a + b + 0\n\n\ndef sub(a, b):\n    return a - b\n\n\ndef neg(a):\n    return -a\n")
    (repo / "parse.py").write_text("def parse(text):\n    return text.split(',')\n")
    (repo / "README.md").write_text("# demo\n\nNow greets by name.\n")
    (repo / ".github/workflows/ci.yml").write_text("on: [push, pull_request]\n")
    (repo / "requirements.txt").write_text("requests==2.31.0\n")
    (repo / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    (repo / "report.pdf").write_bytes(b"\x7fELF\x02\x01\x01" + b"\x00" * 120)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Greet by name")


def main(argv) -> int:
    out = pathlib.Path(argv[1] if len(argv) > 1 else "trace.json").resolve()
    with tempfile.TemporaryDirectory() as d:
        build(pathlib.Path(d))
        return T.main(["--repo", d, "--base", "main", "--head", "agent", "--issue-text", REQUEST, "--out", str(out)])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
