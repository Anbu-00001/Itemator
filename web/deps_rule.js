// Rule 1 of itemator/extras.py (rules v6), new_dependency, for the manifests the browser can weigh: requirements files,
// pyproject.toml and package.json. A line-for-line port of _new_dependencies and the helpers it calls, so that web/green.html
// lists the same dependencies the CI job lists. The Python is the reference: eval/green_agreement.py compares the two on real
// manifest diffs. In the CI job other rules can take a file first (build output, agent files); this file does not read them.
"use strict";
var DepsRule = (function () {
  // ---- Python string helpers ----
  function splitlines(s) {          // str.splitlines(): every line break Python knows, no empty last line
    if (!s) return [];
    var parts = String(s).split(/\r\n|[\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]/);
    if (parts.length && parts[parts.length - 1] === "" && /(?:\r\n|[\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029])$/.test(s)) parts.pop();
    return parts;
  }
  function escape(s) { return s.replace(/[.*+?^${}()|[\]\\\/-]/g, "\\$&"); }
  function base(path) { var i = path.lastIndexOf("/"); return i < 0 ? path : path.slice(i + 1); }
  function dirname(path) { var i = path.lastIndexOf("/"); return i < 0 ? "" : path.slice(0, i).replace(/\/+$/, "") || (path[0] === "/" ? "/" : ""); }
  function dirs(path) { var d = dirname(path); return d ? d.split("/") : []; }
  function startsWithAny(s, list) { return list.some(function (p) { return s.slice(0, p.length) === p; }); }

  function squash(s) { return s.toLowerCase().replace(/-/g, "").replace(/_/g, ""); }

  function mentions(issue, name) {
    if (!name) return false;
    var pairs = [[issue.toLowerCase(), name.toLowerCase()], [squash(issue), squash(name)]];
    for (var i = 0; i < pairs.length; i++) {
      var needle = pairs[i][1];
      if (needle && new RegExp("(?<![a-z0-9])" + escape(needle) + "(?![a-z0-9])").test(pairs[i][0])) return true;
    }
    return false;
  }

  function lines(patch) {          // [sign, text]; sign is "+", "-", " " or "@"
    var out = [];
    splitlines(patch).forEach(function (raw) {
      if (raw.slice(0, 2) === "@@") out.push(["@", raw]);
      else if (raw[0] === "+" || raw[0] === "-" || raw[0] === " ") out.push([raw[0], raw.slice(1)]);
    });
    return out;
  }

  // ---- the parsers ----
  var REQ_LINE = /^\s*([A-Za-z0-9][A-Za-z0-9._\-]*)/;
  var QUOTED_REQ = /["']([A-Za-z0-9][A-Za-z0-9._\-]*)\s*(\[[^\]]*\])?\s*([<>=!~^;@][^"']*)?["']/g;
  var HAS_VERSION = /[<>=~^!]|@\s|\d/;
  var TOML_HEADER = /^\s*\[\[?([^\]]+)\]\]?\s*(#.*)?$/;
  var TOML_KEY = /^\s*(?:"([^"]+)"|'([^']+)'|([A-Za-z0-9][\w.\-]*))\s*=(?!=)\s*(.*)$/;
  var JSON_OPEN = /^\s*"([^"]+)"\s*:\s*\{/;
  var JSON_PAIR = /^\s*"([^"]+)"\s*:\s*"([^"]*)"/;
  var NPM_DEP_KEYS = ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"];
  var NPM_VERSION = /^(\^|~|>=?|<=?|=|\*|x$|latest|next|canary|beta|workspace:|file:|link:|npm:|git|github:|https?:|catalog:|\d)/;
  var NPM_NOT_DEPS = ["name", "version", "main", "module", "types", "typings", "node", "npm", "yarn", "pnpm", "bun", "vscode",
                      "packageManager", "license", "description", "homepage", "author", "type", "browser", "bin", "private", "engines", "electron"];
  var URLISH = /:\/\/|(?<![\w.\-])(?:git|hg|svn|bzr)\+|(?<![\w.\-])(?:github|gitlab|bitbucket|gist):/i;
  var URL_RE = /(?:(?:git|hg|svn|bzr)\+)?[a-z][a-z0-9+.\-]*:\/\/[^\s"',;]+|(?:github|gitlab|bitbucket|gist):[^\s"',;]+/i;
  var NPM_SHORTHAND = /^[\w.\-]+\/[\w.\-]+(#\S*)?$/;
  var ONE_LINE_DEP_KEYS = ["dependencies", "dev-dependencies"];

  function tomlKv(text) {
    var m = TOML_KEY.exec(text);
    return m ? [m[1] || m[2] || m[3], m[4].trim()] : null;
  }

  function urlReqName(s) {
    var m = /[#&]egg=([A-Za-z0-9][\w.\-]*)/.exec(s);
    if (m) return m[1];
    m = /^([A-Za-z0-9][\w.\-]*)\s*(\[[^\]]*\])?\s*@\s*\S/.exec(s);
    if (m) return m[1];
    var u = URL_RE.exec(s);
    if (!u) return null;
    if (s[0] === "-" && !startsWithAny(s, ["-e", "--editable"])) return u[0];
    var last = u[0].split("#")[0].split("?")[0].replace(/\/+$/, "");
    last = last.slice(last.lastIndexOf("/") + 1);
    if (last.slice(-4) === ".git") last = last.slice(0, -4);
    return last || u[0];
  }

  function urlSource(kind, text) {
    if (kind === "npm") {
      var p = JSON_PAIR.exec(text), value = p ? p[2] : "";
      if (new RegExp("^(?:" + URLISH.source + ")", "i").test(value) || new RegExp("^(?:" + URL_RE.source + ")", "i").test(value) || NPM_SHORTHAND.test(value)) return value;
      return null;
    }
    if (!URLISH.test(text)) return null;
    var u = URL_RE.exec(text);
    return u ? u[0] : text.trim();
  }

  function manifestKind(path) {
    var b = base(path);
    if (/^requirements[\w.\-]*\.(txt|in)$/.test(b) || (dirs(path).indexOf("requirements") >= 0 && (b.slice(-4) === ".txt" || b.slice(-3) === ".in")))
      return "requirements";
    return { "pyproject.toml": "pyproject", "package.json": "npm" }[b] || null;
  }

  function depsRequirements(patch) {
    var out = [];
    lines(patch).forEach(function (l) {
      var sign = l[0], text = l[1], s = text.trim();
      if ((sign !== "+" && sign !== "-") || !s || s[0] === "#") return;
      if (URLISH.test(s)) { var name = urlReqName(s); if (name) out.push([sign, name, text]); return; }
      if (s[0] === "-") return;
      var m = REQ_LINE.exec(s);
      if (m) out.push([sign, m[1], text]);
    });
    return out;
  }

  function pyprojectDepArray(section, key) {
    if (section === null || key === null) return false;
    if (section === "project") return key === "dependencies";
    if (section === "project.optional-dependencies" || section === "dependency-groups") return true;
    if (section === "build-system") return key === "requires";
    return key === "dependencies" || key === "dev-dependencies" || section.slice(-12) === "dependencies";
  }

  function depsPyproject(patch) {
    var out = [], section = null, arrayKey = null;
    lines(patch).forEach(function (l) {
      var sign = l[0], text = l[1], q;
      if (sign === "@") { section = null; arrayKey = null; return; }
      var h = TOML_HEADER.exec(text);
      if (h && text.indexOf("=") < 0) { section = h[1].trim().replace(/^"+|"+$/g, ""); arrayKey = null; return; }
      var kv = tomlKv(text);
      if (kv) {
        var key = kv[0], value = kv[1];
        if (value[0] === "[") arrayKey = value.indexOf("]") < 0 ? key : null;
        var depArray = pyprojectDepArray(section, key) ||
          (section === null && ONE_LINE_DEP_KEYS.indexOf(key) >= 0 && value[0] === "[" && value.indexOf("]") >= 0);
        if (section !== null && /(^|\.)(dev-)?dependencies$/.test(section) && section.slice(0, 5) === "tool." && value[0] !== "[") {
          if ((sign === "+" || sign === "-") && key.toLowerCase() !== "python") out.push([sign, key, text]);
          return;
        }
        if (depArray && (sign === "+" || sign === "-")) {
          QUOTED_REQ.lastIndex = 0;
          while ((q = QUOTED_REQ.exec(value)) !== null) out.push([sign, q[1], text]);
        }
        return;
      }
      if (text.trim()[0] === "]") { arrayKey = null; return; }
      if (sign !== "+" && sign !== "-") return;
      QUOTED_REQ.lastIndex = 0;
      q = QUOTED_REQ.exec(text);
      QUOTED_REQ.lastIndex = 0;
      if (!q) return;
      var known = section !== null && arrayKey !== null;
      if (known && pyprojectDepArray(section, arrayKey)) out.push([sign, q[1], text]);
      else if (!known && q[3] && HAS_VERSION.test(q[3])) out.push([sign, q[1], text]);
    });
    return out;
  }

  function npmPairs(patch) {        // [sign, block, key, value, text]
    var out = [], stack = [];
    lines(patch).forEach(function (l) {
      var sign = l[0], text = l[1];
      if (sign === "@") { stack = []; return; }
      var o = JSON_OPEN.exec(text);
      if (o) { if ((text.match(/\{/g) || []).length > (text.match(/\}/g) || []).length) stack.push(o[1]); return; }
      if (/^\s*\}/.test(text)) { if (stack.length) stack.pop(); else stack = ["<top>"]; return; }
      var p = JSON_PAIR.exec(text);
      if (p && (sign === "+" || sign === "-")) out.push([sign, stack.length ? stack[stack.length - 1] : null, p[1], p[2], text]);
    });
    return out;
  }

  function depsNpm(patch) {
    var out = [];
    npmPairs(patch).forEach(function (x) {
      var sign = x[0], block = x[1], key = x[2], value = x[3], text = x[4];
      if (NPM_DEP_KEYS.indexOf(block) >= 0) out.push([sign, key, text]);
      else if (block === null && NPM_NOT_DEPS.indexOf(key) < 0 && NPM_VERSION.test(value)) out.push([sign, key, text]);
    });
    return out;
  }

  var PARSERS = { requirements: depsRequirements, pyproject: depsPyproject, npm: depsNpm };
  var PACKAGE_MANIFESTS = ["npm", "pyproject"];

  function side(patch, keep) {
    return splitlines(patch).filter(function (raw) {
      return startsWithAny(raw, ["@@", " ", keep]) && !startsWithAny(raw, ["+++", "---"]);
    }).join("\n");
  }

  function oldNames(kind, patch) {
    var old = splitlines(patch).filter(function (raw) { return startsWithAny(raw, ["@@", " ", "-"]) && raw.slice(0, 3) !== "---"; })
      .map(function (raw) { return raw.slice(0, 2) === "@@" ? raw : "-" + raw.slice(1); }).join("\n");
    var names = {};
    PARSERS[kind](old).forEach(function (x) { if (x[0] === "-") names[x[1].toLowerCase()] = true; });
    return names;
  }

  function titleAcronyms(issue) {
    var title = issue.trim().split("\n")[0], out = {};
    (title.match(/\b[A-Z][A-Z0-9]{3,}\b/g) || []).forEach(function (a) {
      if ((a.match(/[A-Za-z]/g) || []).length >= 3) out[a.toLowerCase()] = true;
    });
    return Object.keys(out);
  }

  var QUOTED = /^["']([^"']+)["']/;

  function packageName(kind, patch) {
    if (kind === "npm") {
      var hit = npmPairs(patch).filter(function (x) { return x[1] === null && x[2] === "name"; })[0];
      return hit ? hit[3] : null;
    }
    var section = null, found = null;
    lines(patch).some(function (l) {
      var text = l[1], h = TOML_HEADER.exec(text);
      if (h && text.indexOf("=") < 0) { section = h[1].trim().replace(/^"+|"+$/g, ""); return false; }
      var kv = tomlKv(text);
      var m = kv && kv[0] === "name" && ["package", "project", "tool.poetry"].indexOf(section) >= 0 ? QUOTED.exec(kv[1]) : null;
      if (m) { found = m[1]; return true; }
      return false;
    });
    return found;
  }

  function newPackage(issue, f, kind, parse) {
    var deps = {};
    parse(side(f.patch, "+")).forEach(function (x) { if (x[0] === "+") deps[x[1].toLowerCase()] = true; });
    var name = packageName(kind, f.patch), n = Object.keys(deps).length;
    if (!name && !n) return null;
    name = name || base(dirname(f.filename)) || f.filename;
    if (mentions(issue, name) || mentions(issue, name.slice(name.lastIndexOf("/") + 1))) return null;
    return { kind: "new_dependency", path: f.filename, name: name, manifest: kind, newPackage: true,
             why: "adds package " + name + " (a new " + base(f.filename) + " with " + n + " " + (n === 1 ? "dependency" : "dependencies") + "); the issue does not name it" };
  }

  // Every dependency the change adds, each with asked: false when rule 1 lists it as an extra.
  function added(issue, files) {
    issue = issue || "";
    var out = [], acronyms = titleAcronyms(issue);
    files.forEach(function (f) {
      var kind = manifestKind(f.filename || "");
      if (!kind || !f.patch) return;
      var parse = PARSERS[kind];
      if (f.status === "added" && PACKAGE_MANIFESTS.indexOf(kind) >= 0) {
        var e = newPackage(issue, f, kind, parse);
        if (e) out.push(Object.assign({ asked: false }, e));
        return;
      }
      var add = parse(side(f.patch, "+")).filter(function (x) { return x[0] === "+"; });
      var gone = parse(side(f.patch, "-")).filter(function (x) { return x[0] === "-"; });
      var removed = oldNames(kind, f.patch), removedSources = {};
      gone.forEach(function (x) { removed[x[1].toLowerCase()] = true; var s = urlSource(kind, x[2]); if (s !== null) removedSources[s] = true; });
      var seen = {};
      add.forEach(function (x) {
        var name = x[1], text = x[2], low = name.toLowerCase(), source = urlSource(kind, text);
        if (seen[low]) return;
        if (source === null && removed[low]) return;
        if (source !== null && removedSources[source]) return;
        seen[low] = true;
        var row = { kind: "new_dependency", path: f.filename, name: name, manifest: kind, line: text.trim(), source: source };
        if (source !== null) {
          row.asked = issue.toLowerCase().indexOf(source.toLowerCase()) >= 0;
          row.why = row.asked ? "the issue names its source" : "installs " + name + " from " + source + ", not from the package index; the issue does not name that source";
          out.push(row); return;
        }
        var short = kind === "npm" ? name.slice(name.lastIndexOf("/") + 1) : name;
        if (mentions(issue, name) || (short !== name && mentions(issue, short))) { row.asked = true; row.why = "the issue names it"; out.push(row); return; }
        if (acronyms.some(function (a) { return squash(name).indexOf(a) >= 0; })) { row.asked = true; row.why = "the issue's title names what it implements"; out.push(row); return; }
        row.asked = false; row.why = "adds package " + name + "; the issue does not name it";
        out.push(row);
      });
    });
    return out;
  }

  // What rule 1 lists: the same objects as itemator/extras.py's _new_dependencies, for the agreement check.
  function extras(issue, files) {
    return added(issue, files).filter(function (r) { return !r.asked; })
      .map(function (r) { return { kind: r.kind, path: r.path, name: r.name, why: r.why }; });
  }

  // The version a requirements or package.json line pins exactly, else null (the page then weighs the latest).
  function pinned(row) {
    var m;
    if (row.manifest === "npm") { m = /:\s*"=?v?(\d[^"\s^~<>=|*]*)"\s*,?\s*$/.exec(row.line || ""); return m ? m[1] : null; }
    m = /==\s*([A-Za-z0-9._+!-]+)\s*(?:[;#,"'\]]|$)/.exec(row.line || "");
    return m ? m[1] : null;
  }

  return { added: added, extras: extras, pinned: pinned, manifestKind: manifestKind, mentions: mentions, splitlines: splitlines };
})();
if (typeof module !== "undefined" && module.exports) module.exports = DepsRule;
