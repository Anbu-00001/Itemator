// The three added-line checks of itemator/ (moving.py, shapes.py, untrusted.py) and the diff reader of eval/incident_replay.py,
// in plain JavaScript, so that web/try.html can run them in the browser on a pasted diff. The Python is the reference:
// eval/try_agreement.py compares the two on thousands of commits. Keep this file in step with the Python.
"use strict";
var Itemator = (function () {
  var MAX_FOUND = 20, MAX_RUN = 40;

  // ---- the diff reader (eval/incident_replay.py: files_of) ----
  function parseDiff(text) {
    var out = [], blocks = String(text || "").split(/^diff --git /m).slice(1);
    blocks.forEach(function (block) {
      var m = /^a\/(\S+) b\/(\S+)/.exec(block);
      if (!m) return;
      var at = block.indexOf("\n@@");
      var hunks = at >= 0 ? block.slice(at).replace(/^\n+/, "") : "";
      hunks = hunks.split(/^-- $/m)[0];
      var status = /^new file mode/m.test(block) ? "added" : /^deleted file mode/m.test(block) ? "removed" : "modified";
      out.push({ filename: m[2], status: status, patch: hunks, binary: /^(?:Binary files|GIT binary patch)/m.test(block) });
    });
    return out;
  }

  // ---- shared helpers ----
  var SKIP_PATH = new RegExp("(?:^|/)(?:tests?|docs?|spec|specs|__tests__|vendor|node_modules)/|(?:^|/)test_[^/]*$|_test\\.[a-z]+$|\\.(?:md|rst|txt|lock)$|" +
    "(?:^|/)(?:package-lock\\.json|poetry\\.lock|yarn\\.lock|Cargo\\.lock)$", "i");

  function isCiPath(path) {
    var name = path.slice(path.lastIndexOf("/") + 1);
    return name === ".gitlab-ci.yml" || name === ".gitlab-ci.yaml" || /\.gitlab-ci\.ya?ml$/.test(name) ||
      ((path.indexOf(".gitlab/") === 0 || path.indexOf("ci/") === 0) && /\.ya?ml$/.test(name));
  }

  var HUNK = /^@@ -\d+(?:,\d+)? \+(\d+)/;
  function added(patch) { // [[line number in the new file, text]]
    var out = [], n = null;
    String(patch || "").split("\n").forEach(function (line) {
      var m = HUNK.exec(line);
      if (m) n = parseInt(m[1], 10);
      else if (n !== null && line.charAt(0) === "+") { out.push([n, line.slice(1)]); n += 1; }
      else if (n !== null && line.charAt(0) === " ") n += 1;
    });
    return out;
  }

  function addedLines(patch) { // moving.py: added_lines
    var out = [], inHunk = false;
    String(patch || "").split("\n").forEach(function (line) {
      if (line.indexOf("@@") === 0) inHunk = true;
      else if (inHunk && line.charAt(0) === "+") out.push(line.slice(1));
    });
    return out;
  }

  function startsWithAny(s, list) { return list.some(function (p) { return s.indexOf(p) === 0; }); }

  // ---- moving.py ----
  var BRANCHES = "(?:main|master|HEAD|develop|latest|stable|trunk)";
  var IMAGE = /^\s*(?:-\s*)?image:\s*["']?([^\s"'#]+)/;
  var FROM = /^\s*FROM\s+(?:--\S+\s+)?([^\s]+)/i;
  var REF = new RegExp("^\\s*(?:-\\s*)?ref:\\s*[\"']?(" + BRANCHES + ")[\"']?\\s*(?:#.*)?$");
  var REMOTE = new RegExp("^\\s*(?:-\\s*)?(?:remote|file):\\s*[\"']?(\\S*/(?:-/)?(?:raw|blob)/" + BRANCHES + "/\\S*)");
  var COMPONENT = new RegExp("^\\s*(?:-\\s*)?component:\\s*[\"']?(\\S+@(?:~latest|" + BRANCHES + "))[\"']?");
  var PIPE = /\b(?:curl|wget)\b[^|;&]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b/;

  function isBuildFile(path) {
    var name = path.slice(path.lastIndexOf("/") + 1);
    return isCiPath(path) || name.indexOf("Dockerfile") === 0 || /\.Dockerfile$/.test(name) || name === "Containerfile";
  }

  function imageKind(ref) {
    if (startsWithAny(ref, ["$", "${"]) || ref === "scratch") return null;
    var last = ref.slice(ref.lastIndexOf("/") + 1);
    if (last.indexOf(":") < 0) return "untagged";
    return last.slice(last.lastIndexOf(":") + 1) === "latest" ? "latest" : null;
  }

  function moving(files) {
    var found = [];
    for (var i = 0; i < files.length; i++) {
      var f = files[i], path = f.filename || "";
      if (f.status === "removed" || !isBuildFile(path) || !f.patch) continue;
      var dockerfile = !isCiPath(path), lines = addedLines(f.patch);
      for (var j = 0; j < lines.length; j++) {
        var line = lines[j];
        if (line.trimStart().charAt(0) === "#") continue;
        var hit = null, m = (dockerfile ? FROM : IMAGE).exec(line), k;
        if (m && (k = imageKind(m[1]))) {
          if (!(dockerfile && k === "untagged")) hit = ["image-" + k, m[1]];
        }
        if (hit === null && !dockerfile) {
          var kinds = [["include-branch", REF], ["remote-branch", REMOTE], ["component-branch", COMPONENT]];
          for (var q = 0; q < kinds.length; q++) {
            m = kinds[q][1].exec(line);
            if (m) { hit = [kinds[q][0], m[1]]; break; }
          }
        }
        if (hit === null && PIPE.test(line)) hit = ["pipe-to-shell", line.trim().slice(0, 80)];
        if (hit) {
          found.push({ path: path, kind: hit[0], text: hit[1] });
          if (found.length >= MAX_FOUND) return found;
        }
      }
    }
    return found;
  }

  // ---- shapes.py ----
  var SHELL = "(?:sudo\\s+)?(?:ba|z|da|k)?sh\\b";
  var NET = "(?:curl|wget|nc|ncat)\\b";
  var SOURCE_EXT = "(?:ts|tsx|js|jsx|mjs|cjs|py|go|rs|c|cc|cpp|h|java|kt|rb|php|cs)";
  var WHOLE_ENV = "(?:process\\.env(?![.\\[\\w])|os\\.environ(?![.\\[\\w])|os\\.environ\\.copy\\(\\)|dict\\(os\\.environ\\)|Object\\.entries\\(process\\.env\\))";
  function res(list) { return list.map(function (p) { return new RegExp(p, "i"); }); }
  var DECODE = res([
    "base64\\s+(?:-d|-D|--decode)\\b[^\\n]*\\|\\s*" + SHELL,
    "\\b(?:eval|exec)\\s*\\(\\s*(?:atob|base64\\.b64decode|Buffer\\.from\\([^)]*base64|zlib\\.decompress|codecs\\.decode)",
    "\\beval\\s+[\"']?\\$\\([^)]*base64\\s+(?:-d|--decode)",
    "\\bnew\\s+Function\\(\\s*atob\\(",
    "\\b(?:python3?|node|perl|ruby)\\s+-[ce]\\s+[\"'][^\"']*(?:b64decode|atob|base64)"
  ]);
  var ENV = res([
    "\\b(?:env|printenv)\\b(?:\\s+[^|;]*)?\\|\\s*(?:base64\\s*\\|\\s*)?" + NET,
    "\\b(?:curl|wget)\\b[^\\n]*(?:\\s-d|--data(?:-binary|-raw|-urlencode)?|\\s-F\\b|--form|--upload-file|\\s-T)\\b[^\\n]*(?:\\$\\(\\s*(?:env|printenv)\\b|`\\s*(?:env|printenv)\\b)",
    "git\\s+remote\\s+-v[^\\n]*\\|\\s*" + NET,
    NET + "[^\\n]*\\$\\(\\s*git\\s+remote\\s+-v",
    "\\bcat\\s+[^|;\\n]*(?:\\.ssh/|\\.aws/credentials|\\.npmrc|\\.git-credentials|\\.docker/config\\.json)[^|;\\n]*\\|\\s*" + NET
  ]);
  var SEND = /\b(?:fetch|axios\.(?:post|put)|https?\.request|got\.post|requests\.(?:post|put)|urlopen|\.post)\s*\(/i;
  var WHOLE_ENV_RE = new RegExp(WHOLE_ENV);
  var DOWNLOAD = /\b(?:curl|wget)\b|\bfetch\s*\(|requests\.get\s*\(|urllib\.request\.urlopen|https?\.get\s*\(|axios\.get\s*\(|\bdownload\w*\s*\(/i;
  var WRITE = new RegExp("\\bwriteFile(?:Sync)?\\s*\\(|\\bcopyFile(?:Sync)?\\s*\\(|\\bcreateWriteStream\\s*\\(|(?:^|\\s)(?:-o|-O|--output)\\s|[\"'](?:-o|-O|--output)[\"']\\s*,|>\\s*[\"']?[\\w./$-]+\\." + SOURCE_EXT + "\\b");
  var SOURCE_PATH = new RegExp("[\"'][^\"'\\n]*\\." + SOURCE_EXT + "[\"']");
  var REDIRECT = new RegExp("(?:\\s-o|\\s-O|--output|>)\\s*[\"']?[\\w./$-]+\\." + SOURCE_EXT + "\\b");

  function shape(text) {
    if (DECODE.some(function (p) { return p.test(text); })) return "decode-and-run";
    if (ENV.some(function (p) { return p.test(text); }) || (SEND.test(text) && WHOLE_ENV_RE.test(text))) return "env-to-network";
    return null;
  }

  function runsOf(lines) {
    var runs = [], cur = [];
    lines.forEach(function (nt) {
      if (cur.length && nt[0] !== cur[cur.length - 1][0] + 1) { runs.push(cur); cur = []; }
      cur.push(nt);
    });
    if (cur.length) runs.push(cur);
    return runs;
  }

  function shapes(files) {
    var found = [];
    for (var i = 0; i < files.length; i++) {
      var f = files[i], path = f.filename || "";
      if (f.status === "removed" || !f.patch || SKIP_PATH.test(path)) continue;
      var lines = added(f.patch).filter(function (nt) {
        var t = nt[1].trimStart();
        return !startsWithAny(t, ["#", "//"]) || t.indexOf("#!") === 0;
      });
      lines.forEach(function (nt) {
        var kind = shape(nt[1]);
        if (kind) found.push({ path: path, line: nt[0], kind: kind, text: nt[1].trim().slice(0, 80) });
      });
      runsOf(lines).forEach(function (run) {
        for (var s = 0; s < Math.max(1, run.length - MAX_RUN + 1); s++) {
          var win = run.slice(s, s + MAX_RUN);
          var joined = win.map(function (nt) { return nt[1]; }).join("\n");
          if (DOWNLOAD.test(joined) && ((WRITE.test(joined) && SOURCE_PATH.test(joined)) || REDIRECT.test(joined))) {
            var at = win.filter(function (nt) { return DOWNLOAD.test(nt[1]); })[0] || win[0];
            found.push({ path: path, line: at[0], kind: "download-over-source", text: at[1].trim().slice(0, 80) });
            break;
          }
        }
      });
      if (found.length >= MAX_FOUND) return found.slice(0, MAX_FOUND);
    }
    return found;
  }

  // ---- untrusted.py ----
  var GITLAB_VARS = ["CI_COMMIT_MESSAGE", "CI_COMMIT_TITLE", "CI_COMMIT_DESCRIPTION", "CI_COMMIT_AUTHOR", "CI_COMMIT_TAG_MESSAGE",
    "CI_COMMIT_REF_NAME", "CI_COMMIT_BRANCH", "CI_COMMIT_TAG", "CI_MERGE_REQUEST_TITLE", "CI_MERGE_REQUEST_DESCRIPTION",
    "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME", "CI_MERGE_REQUEST_TARGET_BRANCH_NAME", "CI_MERGE_REQUEST_LABELS",
    "CI_MERGE_REQUEST_MILESTONE", "CI_EXTERNAL_PULL_REQUEST_SOURCE_BRANCH_NAME"];
  var VAR_ALT = GITLAB_VARS.join("|");
  var VARRE = new RegExp("\\$(?:\\{(" + VAR_ALT + ")[}:#%/^,-]|(" + VAR_ALT + ")\\b)", "g");
  var EXPRESSION = /\$\{\{(.*?)\}\}/g;
  var STRANGER = new RegExp("github\\.event\\.(?:pull_request\\.(?:title|body|head\\.ref|head\\.label|head\\.repo\\.default_branch)|" +
    "issue\\.(?:title|body)|comment\\.body|review\\.body|review_comment\\.body|discussion\\.(?:title|body)|" +
    "pages\\.[\\w.\\[\\]*]*\\.page_name|head_commit\\.(?:message|author\\.(?:email|name))|" +
    "commits\\[[^\\]]*\\]\\.(?:message|author\\.(?:email|name))|workflow_run\\.(?:head_branch|head_commit\\.(?:message|author\\.(?:email|name))))|" +
    "github\\.head_ref\\b");
  var INTERPRETER = /\b(?:eval|(?:ba|z|da|k)?sh\s+-c|python3?\s+-c|node\s+-e|ruby\s+-e|perl\s+-e|jq|sed|awk|Invoke-Expression|iex)\b/;
  var AGENT = /\b(?:claude|gemini|codex|aider|opencode|cursor-agent|copilot|llm|goose|amp)\b(?:\s|$)/i;
  var KEY = /^\s*(?:-\s+)?([\w.-]+):(?:\s|$)/;
  var SCRIPT_KEYS = ["script", "before_script", "after_script", "run", "entrypoint", "command", "args", "prompt"];

  function isTarget(path) {
    return isCiPath(path) || path.indexOf(".github/workflows/") === 0 || /\.(?:sh|bash)$/.test(path) || /(?:^|\/)action\.ya?ml$/.test(path);
  }

  function pastesStrangerText(text) {
    var re = new RegExp(EXPRESSION.source, "g"), m;
    while ((m = re.exec(text)) !== null) if (STRANGER.test(m[1])) return true;
    return false;
  }

  function inSingleQuotes(line, at) {
    var single = false, dbl = false, i = 0;
    while (i < at) {
      var c = line.charAt(i);
      if (c === "\\" && !single) { i += 2; continue; }
      if (c === "'" && !dbl) single = !single;
      else if (c === '"' && !single) dbl = !dbl;
      i += 1;
    }
    return single;
  }

  function commandLike(line, isScript) {
    if (isScript) return true;
    var m = KEY.exec(line);
    if (m === null) return true;
    return SCRIPT_KEYS.indexOf(m[1]) >= 0;
  }

  function untrusted(files) {
    var found = [];
    for (var i = 0; i < files.length; i++) {
      var f = files[i], path = f.filename || "";
      if (f.status === "removed" || !f.patch || !isTarget(path) || SKIP_PATH.test(path)) continue;
      var script = /\.(?:sh|bash)$/.test(path), lines = added(f.patch);
      for (var j = 0; j < lines.length; j++) {
        var n = lines[j][0], text = lines[j][1];
        if (text.trimStart().charAt(0) === "#") continue;
        var kind = null;
        if (pastesStrangerText(text) && commandLike(text, script)) kind = "github-expression";
        else {
          VARRE.lastIndex = 0;
          var m;
          while ((m = VARRE.exec(text)) !== null) {
            if (inSingleQuotes(text, m.index) || !commandLike(text, script)) continue;
            if (AGENT.test(text)) kind = "agent-prompt";
            else if (INTERPRETER.test(text)) kind = "interpreter";
            if (kind) break;
          }
        }
        if (kind) {
          found.push({ path: path, line: n, kind: kind, text: text.trim().slice(0, 80) });
          if (found.length >= MAX_FOUND) return found;
        }
      }
    }
    return found;
  }

  // ---- what the page says about each kind, in words ----
  var WHAT = {
    "image-latest": "an image tagged `latest`", "image-untagged": "an image with no tag", "include-branch": "an include on a branch",
    "remote-branch": "an include from a branch URL", "component-branch": "a component on a moving version",
    "pipe-to-shell": "a download piped into a shell",
    "decode-and-run": "decodes text and runs it", "env-to-network": "sends the environment or credentials to a server",
    "download-over-source": "downloads a file and writes it over a source file",
    "github-expression": "pastes text a stranger writes into a script before the shell runs it",
    "interpreter": "hands text a stranger writes to an interpreter that runs it",
    "agent-prompt": "puts text a stranger writes into an AI tool's prompt"
  };

  function run(files) { return { moving: moving(files), shapes: shapes(files), untrusted: untrusted(files) }; }

  return { parseDiff: parseDiff, moving: moving, shapes: shapes, untrusted: untrusted, run: run, WHAT: WHAT, added: added };
})();
if (typeof module !== "undefined" && module.exports) module.exports = Itemator;
