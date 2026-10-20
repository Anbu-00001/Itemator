// A public merge request or pull request link, read for web/green.html: its changed files as the rows the rule reads
// ({filename, status, patch}, the CI job's vocabulary) and the text it is checked against. GitLab: the issues the merge request
// closes, as the CI job reads them. GitHub: the issue the pull request's text closes, else the pull request's own title and body,
// as eval/aidev_recall.py's task_text. Read-only GETs without credentials, so only public projects can be read.
"use strict";
var GreenFetch = (function () {
  var MAX_PAGES = 10;            // 100 files a page
  var CLOSES = /\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)\b/i;

  function parseLink(text) {
    var s = String(text || "").trim(), m;
    m = /^https:\/\/gitlab\.com\/((?:[\w.-]+\/)+[\w.-]+)\/-\/merge_requests\/(\d+)(?:[/?#].*)?$/.exec(s);
    if (m) return { host: "gitlab", project: m[1], number: Number(m[2]) };
    m = /^https:\/\/github\.com\/([\w.-]+)\/([\w.-]+)\/pull\/(\d+)(?:[/?#].*)?$/.exec(s);
    if (m) return { host: "github", owner: m[1], repo: m[2], number: Number(m[3]) };
    return null;
  }

  function gitlabStatus(d) {
    return d.new_file ? "added" : d.deleted_file ? "removed" : d.renamed_file ? "renamed" : "modified";
  }

  // get(url) -> {status, json}, as web/weigh.js's browserGet without wantLength
  async function pages(get, base) {
    var out = [];
    for (var page = 1; page <= MAX_PAGES; page++) {
      var r = await get(base + (base.indexOf("?") < 0 ? "?" : "&") + "per_page=100&page=" + page, false);
      if (r.status !== 200) return { status: r.status, rows: out };
      out = out.concat(r.json || []);
      if (!r.json || r.json.length < 100) return { status: 200, rows: out };
    }
    return { status: 200, rows: out, truncated: true };
  }

  async function fromGitlab(get, link) {
    var api = "https://gitlab.com/api/v4/projects/" + encodeURIComponent(link.project) + "/merge_requests/" + link.number;
    var d = await pages(get, api + "/diffs");
    if (d.status !== 200) return { error: d.status === 404 ? "not found, or not public" : "GitLab answered " + d.status };
    var files = d.rows.map(function (x) {
      return { filename: x.new_path, status: gitlabStatus(x), patch: x.diff || "", too_large: !!(x.too_large || x.collapsed) };
    });
    var issues = await get(api + "/closes_issues", false);
    var list = issues.status === 200 ? issues.json || [] : [];
    return { files: files, truncated: !!d.truncated, skipped: files.filter(function (f) { return f.too_large; }).map(function (f) { return f.filename; }),
             issue: list.map(function (i) { return (i.title || "") + "\n" + (i.description || ""); }).join("\n\n"),
             issueFrom: list.length ? "the " + (list.length === 1 ? "issue" : list.length + " issues") + " it closes" : "none (it closes no issue)" };
  }

  async function fromGithub(get, link) {
    var api = "https://api.github.com/repos/" + link.owner + "/" + link.repo;
    var pr = await get(api + "/pulls/" + link.number, false);
    if (pr.status !== 200) return { error: pr.status === 404 ? "not found, or not public" : pr.status === 403 ? "GitHub's hourly limit for this browser is used up; try later" : "GitHub answered " + pr.status };
    var d = await pages(get, api + "/pulls/" + link.number + "/files");
    if (d.status !== 200) return { error: "GitHub answered " + d.status + " for the files" };
    var files = d.rows.map(function (x) { return { filename: x.filename, status: x.status, patch: x.patch || "", too_large: !x.patch && x.changes > 0 }; });
    var body = (pr.json && pr.json.body) || "", title = (pr.json && pr.json.title) || "";
    var m = CLOSES.exec(body), issue = null;
    if (m) {
      var r = await get(api + "/issues/" + m[1], false);
      if (r.status === 200 && r.json && (r.json.title || r.json.body)) issue = r.json;
    }
    return { files: files, truncated: !!d.truncated || d.rows.length >= 3000, skipped: files.filter(function (f) { return f.too_large; }).map(function (f) { return f.filename; }),
             issue: issue ? (issue.title || "") + "\n" + (issue.body || "") : title + "\n" + body,
             issueFrom: issue ? "issue #" + m[1] + ", which it closes" : "the pull request's own title and text (it closes no issue)" };
  }

  function read(get, link) { return link.host === "gitlab" ? fromGitlab(get, link) : fromGithub(get, link); }

  return { parseLink: parseLink, read: read, CLOSES: CLOSES };
})();
if (typeof module !== "undefined" && module.exports) module.exports = GreenFetch;
