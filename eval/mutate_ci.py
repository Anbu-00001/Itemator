"""Mutation test for the CI job (T11, T12a, T17, T22): break the state logic, the injection scan, the
diff, the line counting and anchors, the thread stub or the job-log copy in a copy of
itemator/ci.py, or the registry facts in a copy of itemator/registry.py; tests/test_ci.py (T11
mutants), tests/test_ci_anchors.py (T12a mutants) or tests/test_registry.py (T17 and T22 mutants) must
fail for every mutant.

Usage (WORK must be outside the repository, or pytest would collect the copies):
    .venv/bin/python -I eval/mutate_ci.py "$PWD" /tmp/itemator-ci-mutants [T17]
With T17, only the T17 mutants run (every anchor of every mutant is still checked first).
Exit status 0 only when every mutant is killed.
"""
import pathlib, shutil, subprocess, sys
REPO = pathlib.Path(sys.argv[1]); WORK = pathlib.Path(sys.argv[2])
PY = str(REPO / ".venv/bin/python")
M = [
 # ---- state logic
 ("state: no_issue dropped", '    if not issues:\n        return "no_issue"\n', ""),
 ("state: author check any()", 'and all(i["author_id"] == mr_author_id for i in issues)', 'and any(i["author_id"] == mr_author_id for i in issues)'),
 ("state: author check dropped", '    if _author_wrote(issues, mr_author_id):\n        return "author_wrote_issue"\n', ""),
 ("state: author outranks extras", '    if analysis.extras:                      # the extras are the point; the author note rides along as a caveat\n', '    if analysis.extras and not _author_wrote(issues, mr_author_id):\n'),
 ("state: extras dropped", '    if analysis.extras:                      # the extras are the point; the author note rides along as a caveat\n        return "extras"\n', ""),
 ("card: caveat dropped", '"caveat_line": caveat,', '"caveat_line": None,'),
 ("card: caveat repeats the final line", 'state in ("extras", "unplaced_only", "inside_ask")', 'True'),
 ("state: unplaced_only dropped", '    if analysis.unplaced:\n        return "unplaced_only"\n', ""),
 ("state: no_issue keeps extras", 'found = [] if state == "no_issue" else analysis.extras', "found = analysis.extras"),
 ("issues: closes_issues ignored", "    if closes:\n", "    if False:\n"),
 ("issues: description fallback dropped", "    for n in closing_refs(description):", "    for n in []:"),
 ("api: token sent first", "status, body = self.http(url, {})", 'status, body = self.http(url, {"JOB-TOKEN": self.token} if self.token else {})'),
 ("card: singular wrong", '"Skim this file." if n == 1 else', '"Skim this file." if n == 0 else'),
 ("card: injection line dropped", '"injection_line": INJECTION_LINE if injection else None}', '"injection_line": None}'),
 # ---- injection scan
 ("scan: removed lines scanned", '        elif line.startswith("+"):\n            yield', '        elif line.startswith(("+", "-")):\n            yield'),
 ("scan: context lines not counted", '        elif line.startswith(" "):\n            n += 1', '        elif line.startswith(" "):\n            pass'),
 ("scan: ignore_previous dropped", '("ignore_previous", r"', '("ignore_previous", r"(?!x)x'),
 ("scan: reviewer_approve dropped", '("reviewer_approve", r"', '("reviewer_approve", r"(?!x)x'),
 ("scan: system_prompt dropped", '("system_prompt", r"', '("system_prompt", r"(?!x)x'),
 ("scan: invisible chars kept", 'plain = _INVISIBLE.sub("", text)', "plain = text"),
 ("scan: tag range off", r'_TAG = re.compile("[\U000E0000-\U000E007F]")', r'_TAG = re.compile("[\U000E0080-\U000E00FF]")'),
 ("scan: bidi dropped", "if _BIDI.search(line):", "if False:"),
 ("scan: comment addressee not required", "(_ADDRESSEE.search(body) and _IMPERATIVE.search(body))", "_IMPERATIVE.search(body)"),
 ("scan: html comments dropped", "for m in _COMMENT.finditer(joined):", "for m in []:"),
 ("scan: comment line from its end", 'starts[joined.count("\\n", 0, m.start())]', 'starts[joined.count("\\n", 0, m.end())]'),
 ("scan: agent config dropped", "if any(_is_agent_config(p) for p in paths):", "if False:"),
 ("scan: rename source ignored", 'paths = {f["filename"], f.get("previous_filename") or f["filename"]}', 'paths = {f["filename"]}'),
 ("scan: flow YAML not config", 'or ("flows" in parts[:-1] and base.endswith((".yml", ".yaml"))))', "or False)"),
 # ---- diff
 ("diff: binary flag dropped", '            f["binary"] = True', "            pass"),
 ("diff: previous_filename dropped", '            f["previous_filename"] = old', "            pass"),
]

# T12a: anchors (line counting, which line, which paths), thread stubs, the job-log copy
A = [
 # ---- line counting
 ("anchors: hunk start off by one", "old, new = int(m.group(1)), int(m.group(2))", "old, new = int(m.group(1)), int(m.group(2)) + 1"),
 ("anchors: old and new starts swapped", "old, new = int(m.group(1)), int(m.group(2))", "new, old = int(m.group(1)), int(m.group(2))"),
 ("anchors: hunk header ignored", "                old, new = int(m.group(1)), int(m.group(2))\n", "                pass\n"),
 ("anchors: context lines not counted", '            yield " ", old, new, line[1:]\n            old += 1\n            new += 1\n', '            yield " ", old, new, line[1:]\n'),
 ("anchors: context counted on one side", '            yield " ", old, new, line[1:]\n            old += 1\n            new += 1\n', '            yield " ", old, new, line[1:]\n            new += 1\n'),
 ("anchors: removed lines counted as new", '            yield "-", old, None, line[1:]\n            old += 1\n', '            yield "-", old, None, line[1:]\n            old += 1\n            new += 1\n'),
 ("anchors: added lines counted as old", '            yield "+", None, new, line[1:]\n            new += 1\n', '            yield "+", None, new, line[1:]\n            new += 1\n            old += 1\n'),
 ("anchors: removed lines not counted", '            yield "-", old, None, line[1:]\n            old += 1\n', '            yield "-", old, None, line[1:]\n'),
 ("anchors: no-newline marker counted", r'        if line.startswith("\\"):' + "\n            continue\n", ""),
 ("anchors: trailing blank line kept", '    if lines[-1] == "":\n        lines.pop()\n', ""),
 ("anchors: context line anchored", "if sign in signs and (matches", 'if sign in signs + " " and (matches'),
 # ---- which line
 ("anchors: dependency not matched by name", "            matches = _names(e.name)\n", "            matches = None\n"),
 ("anchors: name boundary after dropped", r'+ r"(?![A-Za-z0-9])"', '+ ""'),
 ("anchors: name boundary before dropped", r'r"(?<![A-Za-z0-9])" + ', '"" + '),
 ("anchors: name separators exact", r'r"[-_.]*".join(parts)', '"-".join(parts)'),
 ("anchors: name case-sensitive", ", re.I).search", ").search"),
 ("anchors: npm script not matched by key", """            matches = lambda text: f'"{e.name}"' in text\n""", "            matches = None\n"),
 ("anchors: tests anchor on any removed line", 'signs, matches = "-", (X._ASSERT if "assertion lines" in e.why else X._TEST_DEF).search', 'signs, matches = "-", None'),
 ("anchors: assertions anchor on the definition", '"assertion lines" in e.why else', 'False else'),
 ("anchors: tests anchor on added lines", 'signs, matches = "-", (X._ASSERT', 'signs, matches = "+", (X._ASSERT'),
 ("anchors: symbol not matched", 'signs, matches = "-", lambda text: e.name in X._symbols(text, ext)', 'signs, matches = "-", None'),
 ("anchors: added kinds anchor on removed lines", '        signs, matches = "+", None\n', '        signs, matches = "-", None\n'),
 ("anchors: no fallback to the other sign", " or _first_line(f, signs) or _first_line(f, other)", " or _first_line(f, signs)"),
 ("anchors: no fallback to any line of the sign", " or _first_line(f, signs) or _first_line(f, other)", " or _first_line(f, other)"),
 ("anchors: mass event anchors on its directory", "f = by_path.get(e.detail[0] if e.detail else e.path)", "f = by_path.get(e.path)"),
 ("anchors: mass event anchors on its last file", "by_path.get(e.detail[0] if", "by_path.get(e.detail[-1] if"),
 # ---- which paths, which files get none
 ("anchors: rename source ignored", '"old_path": f.get("previous_filename") or f["filename"]', '"old_path": f["filename"]'),
 ("anchors: rename target ignored", '"new_path": f["filename"],\n                    "old_line"', '"new_path": f.get("previous_filename") or f["filename"],\n                    "old_line"'),
 ("anchors: binary flag ignored", 'if f.get("binary") or not patch:', "if not patch:"),
 ("anchors: size limit off by one", "> MAX_PATCH_BYTES:", ">= MAX_PATCH_BYTES:"),
 ("anchors: size limit dropped", 'if len(patch.encode("utf-8", "replace")) > MAX_PATCH_BYTES:', "if False:"),
 ("anchors: missing file reason", 'return None, "file not in the diff"', 'return None, "no text patch"'),
 ("anchors: extras carry none", '"extras": [describe_extra(e, by_path, items, r) for (e, items), r in zip(grouped, registry)],', '"extras": [{**e.to_dict(), "detail": list(e.detail)} for e, _ in grouped],'),
 # ---- stub, plain facts
 ("stub: no closing full stop", '    if not why.endswith((".", "!", "?")):\n        why += "."\n', ""),
 ("stub: double full stop", 'if not why.endswith((".", "!", "?")):', "if True:"),
 ("stub: kind instead of label", '({_label(e)}): {why}', '({e.kind}): {why}'),
 ("plain facts: detail count wrong", '"detail_count": len(e.detail)', '"detail_count": 0'),
 # ---- job log
 ("log: markers not escaped", r'.replace("<", "\\u003c").replace(">", "\\u003e")', ""),
 ("log: size limit ignored", "    if len(text) > limit:\n", "    if False:\n"),
 ("log: detail kept in the compact copy", 'c = {**report, "extras": [{k: v for k, v in e.items() if k != "detail"} for e in report["extras"]]}', "c = dict(report)"),
 ("log: truncated flag missing", 'text = _one_line({**c, "truncated": cut})', "text = _one_line(c)"),
 ("log: long lists never cut", "if size() > limit and len(c[key]) > 20:", "if False:"),
 ("log: plain facts never cut", '        if size() > limit:\n            c["extras"] = [{k: v for k, v in e.items() if k != "plain_facts"}', '        if False:\n            c["extras"] = [{k: v for k, v in e.items() if k != "plain_facts"}'),
 ("log: extras dropped all at once", 'c["extras"] = c["extras"][:len(c["extras"]) // 2]', 'c["extras"] = []'),
 ("log: extras total not recorded", '            c["extras_total"] = n\n', ""),
 ("log: job prints no block", "    print(log_block(report))\n", ""),
 # ---- T15: grouping on the card (rules v4), the new kinds
 ("group: off", "        if key is None or len(pools[key]) < GROUP:\n", "        if True:\n"),
 ("group: threshold 7", "GROUP = 6 ", "GROUP = 7 "),
 ("group: threshold 5", "GROUP = 6 ", "GROUP = 5 "),
 ("group: kinds mixed", "    return e.kind, (e.path if", "    return (e.path if"),
 ("group: named kinds by directory", 'e.path if e.name != e.path else posixpath.dirname(e.path) + "/")', 'posixpath.dirname(e.path) + "/")'),
 ("group: first item not the anchor", "anchor_for(items[0] if items else e, by_path)", "anchor_for(e, by_path)"),
 ("group: items not in plain facts", '        plain["detail"] = [i.to_dict() for i in items]\n', "        pass\n"),
 ("group: card shows every item", "card_lines(state, issues, [e for e, _ in grouped]", "card_lines(state, issues, found"),
 ("group: why without names", 'f"{len(items)} {_PLURAL.get(e.kind, e.kind)} in {where}: " + ", ".join(i.name for i in items)', 'f"{len(items)} {_PLURAL.get(e.kind, e.kind)} in {where}"'),
 ("label: grouped unit always files", '    unit = "files" if e.path.endswith("/") or e.kind == "version_bump" else _UNIT.get(e.kind, "names")', '    unit = "files"'),
 ("label: version bump unit", ' or e.kind == "version_bump" else', " else"),
 ("label: version bump unlabelled", '"version_bump": "version bump",', ""),
 ("anchors: version not matched", '        elif e.kind == "version_bump":\n            matches = lambda text: e.name in text\n', ""),
 ("log: block printed before the card", '    print(report["card"]["final_line"])\n    print(report["card"]["todo_line"])\n    print(log_block(report))\n', '    print(log_block(report))\n    print(report["card"]["final_line"])\n    print(report["card"]["todo_line"])\n'),
]
# T17: registry facts. RG mutants break itemator/registry.py; RC mutants break its wiring in itemator/ci.py.
RG = [
 ("names: prefix match", "_NAME[ecosystem].fullmatch(name) is not None", "_NAME[ecosystem].match(name) is not None"),
 ("names: npm case-insensitive", '[a-z0-9~-][a-z0-9._~-]*/)?[a-z0-9~-][a-z0-9._~-]*")', '[a-z0-9~-][a-z0-9._~-]*/)?[a-z0-9~-][a-z0-9._~-]*", re.I)'),
 ("names: length cap dropped", "0 < len(name) <= NAME_MAX", "0 < len(name)"),
 ("names: length cap off by one", "0 < len(name) <= NAME_MAX", "0 < len(name) < NAME_MAX"),
 ("url: PyPI name not normalised", "quote(_pep503(name), safe='')", "quote(name, safe='')"),
 ("url: npm scope slash not quoted", 'quote(name, safe="@")', 'quote(name, safe="@/")'),
 ("hosts: check dropped", 'if parts.scheme != "https" or parts.hostname not in HOSTS:', "if False:"),
 ("hosts: http allowed", 'if parts.scheme != "https" or parts.hostname not in HOSTS:', "if parts.hostname not in HOSTS:"),
 ("budget: full timeout whatever is left", "min(TIMEOUT, left)", "TIMEOUT"),
 ("budget: total dropped", "        if left <= 0:\n", "        if False:\n"),
 ("cap: off by one", "if self.looked >= MAX_PACKAGES:", "if self.looked > MAX_PACKAGES:"),
 ("cap: six of a group", "members[:PER_EXTRA]", "members[:PER_EXTRA + 1]"),
 ("404: not a fact", "            if status == 404:\n", "            if False:\n"),
 ("osv: pinned version not sent", '            query["version"] = rec["version"]', "            pass"),
 ("osv: advisories miscounted", 'rec["advisories"] = _distinct(vulns)', 'rec["advisories"] = min(_distinct(vulns), 1)'),
 ("osv: aliases counted again", "        if not ids & seen:\n", "        if True:\n"),
 ("osv: odd ids kept", " and _ADVISORY_ID.fullmatch(v[\"id\"])][:20]", "][:20]"),
 ("osv: more pages ignored", 'rec["advisories_partial"] = True', "pass"),
 ("osv: PyPI name not normalised", '_pep503(name) if eco == "PyPI" else name', "name"),
 ("osv: errors escape", '            rec["advisories"], rec["advisories_reason"] = None, _reason(ex)', "            raise"),
 ("pypi: first release from the last file", "first = dates[0] if dates else None", "first = dates[-1] if dates else None"),
 ("pypi: name check dropped", 'if _pep503(str(info.get("name") or "")) != _pep503(name):', "if False:"),
 ("npm: name check dropped", 'if doc.get("name") != name:', "if False:"),
 ("npm: licence object kept", '        lic = lic.get("type")', "        lic = str(lic)"),
 ("crates: name check dropped", 'if crate.get("name") != name:', "if False:"),
 ("card: singular advisory", "advisor{'y' if a == 1 else 'ies'}", "advisor{'ies'}"),
 ("card: unavailable says nothing", '            return "Registry facts could not be read."', "            return None"),
 ("card: unread count dropped", "    if len(shown) > len(ok):\n", "    if False:\n"),
 ("card: pinned version not shown", '(f" for {p[\'version\']}" if p.get("version") else " in any version")', '""'),
 ("card: unpinned count not marked", 'else " in any version")', 'else "")'),
 ("pin: wildcard accepted", "(?![0-9A-Za-z.+!_*=-])", "(?![0-9A-Za-z+!_=-])"),
 ("pin: name glued to another", 'rx = (r"(?<![A-Za-z0-9._-])" + ', "rx = ("),
 ("skip: own package looked up", 'if (by_path.get(e.path) or {}).get("status") == "added" and kind in X._PACKAGE_MANIFESTS:', "if False:"),
 ("skip: URL source looked up", 'if "not from the package index" in e.why:', "if False:"),
 ("skip: local path looked up", "    if _local(eco, e.name, line):", "    if False:"),
 ("skip: other ecosystems tried", 'SUPPORTED = ("PyPI", "npm", "crates.io")', 'SUPPORTED = ("PyPI", "npm", "crates.io", "Go")'),
 ("redirect: other hosts followed", "new.hostname != old.hostname or ", ""),
 ("redirect: http followed", 'new.scheme != "https" or ', ""),
 ("redirect: handler not installed", "_OPENER = urllib.request.build_opener(_SameHost)", "_OPENER = urllib.request.build_opener()"),
 ("fetch: no User-Agent", 'headers = {"Accept": "application/json", "User-Agent": USER_AGENT}', 'headers = {"Accept": "application/json"}'),
 ("fetch: timeout read as network", 'raise LookupFailed("timeout" if isinstance(e.reason, TimeoutError) else "network") from e', 'raise LookupFailed("network") from e'),
 ("fetch: HTTP error raised", '        return e.code, b""', '        raise LookupFailed("network")'),
 ("job: lookup errors escape the record", "        except Exception as ex:          # never fail the job because of a lookup", "        except LookupFailed as ex:"),
 ("job: broken request escapes", "            except Exception as ex:\n                packages.append(", "            except LookupFailed as ex:\n                packages.append("),
 # ---- T22: the T21 audit's findings (licence shape, bounds, network location, deadline, caps, long lines, honesty)
 ("licence: shape not required", "_SPDX.fullmatch(text) is not None and ", ""),
 ("licence: parentheses unbalanced", 'text.count("(") == text.count(")")', "True"),
 # retired after the SPDX allowlist: "licence: stray dot allowed" is now equivalent (the allowlist refuses every id this guard caught; the guard stays as defence in depth)
 # retired after the SPDX allowlist: "licence: hyphenated phrase shown" is now equivalent (the allowlist refuses every id this guard caught; the guard stays as defence in depth)
 ("licence: six terms", '\\)*){0,4}")', '\\)*){0,5}")'),
 ("licence: ids not checked against the common list", " and _known_ids(text))", ")"),
 ("licence: slash form not read", 'return " OR ".join(parts) if len(parts) > 1 and all(x in COMMON_SPDX for x in parts) else text', "return text"),
 ("licence: unknown id after + allowed", 'or (t.endswith("+") and t[:-1] in COMMON_SPDX)', "or t.endswith('+')"),
 ("licence: UNKNOWN stated", ' and t.upper() != "UNKNOWN"', ""),
 ("licence: whitespace kept", '[_slash_as_or(" ".join(v.split())) for v in stated', "[_slash_as_or(v.strip()) for v in stated"),
 ("licence: classifier not shown", 'return {"license": named, "license_form": "classifier"}', 'return {"license": named, "license_form": "free_text"}'),
 ("licence: odd classifier shown", "all(_CLASSIFIER.fullmatch(c) and not _addressed(c) for c in classifiers)", "True"),
 ("licence: free text shown", "    elif _shows_licence(p):", "    elif True:"),
 ("licence: publisher not named", "DECLARED if declare else ''", "''"),
 ("licence: publisher named every time", "_facts(p, not declared)", "_facts(p)"),
 ("pypi: classifiers ignored", ', info.get("license")], classifiers)', ', info.get("license")])'),
 ("pypi: licence expression ignored", '[info.get("license_expression"), info.get("license")]', '[info.get("license")]'),
 ("pypi: classifier group shown", "    classifiers = [c for c in classifiers if c not in _GROUPS]\n", ""),
 ("pypi: versions without files counted", "files.items() if fs}", "files.items()}"),
 ("pypi: yanked releases counted", ' if not all(f.get("yanked") is True for f in fs)', ""),
 ("card: yanked not said", '    if p.get("yanked"):\n', "    if False:\n"),
 ("npm: legacy licenses ignored", 'if lic is None and isinstance(meta.get("licenses"), list):', "if False:"),
 ("npm: unpublished read", 'if times.get("unpublished"):', "if False:"),
 ("crates: num_versions ignored", '_count(crate.get("num_versions"))', "None"),
 ("count: no upper bound", "0 <= n < MAX_COUNT", "0 <= n"),
 ("count: negative counted", "0 <= n < MAX_COUNT", "n < MAX_COUNT"),
 ("count: bool counted", "type(n) is int", "isinstance(n, int)"),
 ("card: count not checked", "if _count(n) is not None else", "if isinstance(n, int) else"),
 ("version: no length cap", 'r"[A-Za-z0-9._+!-]{1,64}"', 'r"[A-Za-z0-9._+!-]+"'),
 ("version: any characters", 'r"[A-Za-z0-9._+!-]{1,64}"', 'r"[^\\n]{1,64}"'),
 ("pin: version not checked", "return v if v and _VERSION.fullmatch(v) else None", "return v"),
 ("date: impossible day shown", "datetime.date.fromisoformat(s).isoformat()", "s"),
 ("date: shape not required", 're.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", s)', "True"),
 ("lines: pin read on a long line", "    if len(line) > MAX_LINE:\n        return None\n", ""),
 ("lines: path read on a long line", "    if len(line) > MAX_LINE:\n        return False\n", ""),
 ("netloc: any port", "port in (None, 443) and ", ""),
 ("netloc: user part allowed", '"@" not in parts.netloc and ', ""),
 ("netloc: bad port allowed", "    except ValueError:\n        return False\n", "    except ValueError:\n        return True\n"),
 ("netloc: not checked on a request", '        if not _plain_netloc(parts):\n            raise LookupFailed("host")\n', ""),
 ("netloc: not checked on a redirect", '        if not _plain_netloc(new):\n            raise LookupFailed("redirect")\n', ""),
 ("deadline: read waits for 64 KB", "response.read1(65536)", "response.read(65536)"),
 ("deadline: not checked while reading", "        if _clock() > deadline:\n", "        if False:\n"),
 ("body: one cap for every host", "cap = MAX_BODY.get(urllib.parse.urlsplit(url).hostname, 2 ** 20)", "cap = 64 * 2 ** 20"),
 ("body: Content-Length not checked", "            if declared > cap:\n", "            if False:\n"),
 ("body: cap dropped", "        if size > cap:", "        if False:"),
 ("honesty: registry not named", "on {_SITE[p['ecosystem']]} was found\"", "was found\""),
 ("honesty: junk advisories counted", 'if not isinstance(v, dict) or not isinstance(v.get("id"), str):', "if not isinstance(v, dict):"),
]
RC = [
 ("stub: registry sentence dropped", "thread_stub(e, RG.sentence(registry))", "thread_stub(e)"),
 ("stub: sentence after the replies", '{why}{facts} To keep it, reply with its exact name. "', '{why} To keep it, reply with its exact name.{facts} "'),
 ("plain_facts: registry dropped", '        plain["registry"] = registry', "        pass"),
 ("job: registries not asked by default", "registry_fetch or RG.fetch", "registry_fetch"),
 ("facts: fetcher ignored", "registry = RG.look_up(grouped, by_path, registry_fetch, now) if registry_fetch else [None] * len(grouped)", "registry = [None] * len(grouped)"),
 # ---- T22: names with a backtick or a control character (T21 FIX 2)
 ("name: backtick kept", 'r"[`\\x00-', 'r"[\\x00-'),
 ("name: C0 controls kept", "\\x00-\\x1f\\x7f", "\\x0a\\x0d\\x7f"),
 ("name: C1 controls kept", "\\x7f-\\x9f]", "\\x7f]"),
 ("name: a run becomes one apostrophe", '\\x9f]")', '\\x9f]+")'),
 ("stub: raw name in the code span", 'return f"`{shown_name(text)}`"', 'return f"`{text}`"'),
 ("stub: reason keeps backticks", "why = shown_name(e.why).strip()", 'why = re.sub(r"[\\r\\n]+", " ", e.why).strip()'),
 ("card: raw name on the final line", 'names = ", ".join(f"{_code(e.name)} (', 'names = ", ".join(f"`{e.name}` ('),
 ("json: raw_name dropped", 'rec["name"], rec["raw_name"] = plain["name"], e.name', 'rec["name"] = plain["name"]'),
 ("json: raw name kept as name", 'rec["name"], rec["raw_name"] = plain["name"], e.name', 'rec["raw_name"] = e.name'),
 ("plain_facts: raw name", '"name": shown_name(e.name)', '"name": e.name'),
]
SRC = {"itemator/ci.py": (REPO / "itemator/ci.py").read_text(), "itemator/registry.py": (REPO / "itemator/registry.py").read_text()}
JOBS = ([(*m, "itemator/ci.py", "tests/test_ci.py") for m in M] + [(*m, "itemator/ci.py", "tests/test_ci_anchors.py") for m in A]
        + [(*m, "itemator/ci.py", "tests/test_registry.py") for m in RC] + [(*m, "itemator/registry.py", "tests/test_registry.py") for m in RG])
for label, old, new, path, _ in JOBS:
    assert SRC[path].count(old) == 1, f"mutant {label!r}: anchor found {SRC[path].count(old)} times in {path}"
if sys.argv[3:] == ["T17"]:
    JOBS = [j for j in JOBS if j[4] == "tests/test_registry.py"]
def run(i, path, text, tests):
    d = WORK / f"m{i:02d}"
    if d.exists(): shutil.rmtree(d)
    for sub in ("itemator", "tests", "tools"):
        shutil.copytree(REPO / sub, d / sub, ignore=shutil.ignore_patterns("__pycache__"))
    (d / path).write_text(text)
    return subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", tests], cwd=d, capture_output=True, text=True)
for target in sorted({j[4] for j in JOBS}):
    base = run(99, "itemator/ci.py", SRC["itemator/ci.py"], target)
    if base.returncode != 0:
        print(f"the unmutated copy fails {target}, so no mutant can be judged:\n" + base.stdout[-2000:]); sys.exit(2)
survivors = 0
for i, (label, old, new, path, target) in enumerate(JOBS):
    r = run(i, path, SRC[path].replace(old, new), target)
    failed = [l.split("::")[1].split(" ")[0] for l in r.stdout.splitlines() if l.startswith("FAILED")]
    killed = r.returncode != 0
    survivors += not killed
    print(f"{'KILLED ' if killed else 'SURVIVED'} {label:46s} {','.join(failed)[:150]}")
total = len(JOBS)
print(f"{total - survivors}/{total} mutants killed")
sys.exit(1 if survivors else 0)
