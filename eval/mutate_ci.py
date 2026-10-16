"""Mutation test for the CI job (T11, T12a, T17, T22, T20, T23, T26, T35, T40): break the state logic, the injection scan, the
diff, the line counting and anchors, the thread stub or the job-log copy in a copy of
itemator/ci.py, the registry facts in a copy of itemator/registry.py, or the team policy in a copy of
itemator/policy.py; tests/test_ci.py (T11 mutants), tests/test_ci_anchors.py (T12a mutants),
tests/test_registry.py (T17 and T22 mutants) or tests/test_policy.py (T20 mutants) must fail for every mutant;
each T26 mutant names its own test file (tests/test_diff_attributes.py, tests/test_answers.py, tests/test_policy.py);
T35 mutants break itemator/said.py or its wiring in itemator/ci.py and are judged by tests/test_said.py.
T40 mutants break the `always` offer in itemator/ci.py (judged by tests/test_answers.py) or the react prompt in
flows/itemator_react.yml (judged by tests/test_react_prompt.py, which parses it with a YAML parser).
T45 mutants break `names.asker_required` in itemator/policy.py and itemator/ci.py (judged by tests/test_asker.py).
T46 mutants break the asker rule and the issue receipt of flows/itemator_react.yml (judged by
tests/test_react_prompt.py); its approval-step mutants were retired with the step itself (T51).
T51 mutants put an approval back into the react prompt (each forbidden word, the old header, the slash exception,
the Step 8 field), each killed by tests/test_react_prompt.py::test_the_flow_never_approves; three more are the
non-approval T46 mutants of the same lines with updated anchors.

Usage (WORK must be outside the repository, or pytest would collect the copies):
    .venv/bin/python -I eval/mutate_ci.py "$PWD" /tmp/itemator-ci-mutants [T17|T35|T40|T42|T43|T44|T45|T46|T51|T52|T53|T54|T55]
With T17 (or T35, T40), only those mutants run (every anchor of every mutant is still checked first).
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
 ("card: todo without remove (T23)", ', "remove" to drop it.\'', ".'"),
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
 ("anchors: extras carry none", '"extras": [describe_extra(e, by_path, items, r, other, s, always, askers) for ((e, items), r), s in zip(kept, said)],', '"extras": [{**e.to_dict(), "detail": list(e.detail)} for ((e, _), _), s in zip(kept, said)],'),   # T35: anchor follows the new line
 # ---- stub, plain facts
 ("stub: no closing full stop", '    if not why.endswith((".", "!", "?")):\n        why += "."\n', ""),
 ("stub: double full stop", 'if not why.endswith((".", "!", "?")):', "if True:"),
 ("stub: kind instead of label", '({_label(e)}): {why}', '({e.kind}): {why}'),
 ("stub: remove answer dropped (T23)", "To drop it from this MR, reply `remove`. ", ""),
 ("stub: remove not in backticks (T23)", "reply `remove`.", "reply remove."),
 ("stub: remove after the dismissal (T23)",
  'f"{split}{remove}{always}If this is not really an extra, reply `not an extra`.")',       # T40: anchor follows the new line
  'f"{split}{always}If this is not really an extra, reply `not an extra`. {remove}")'),
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
 ("group: card shows every item", "card_lines(state, issues, [e for (e, _), _ in kept]", "card_lines(state, issues, found"),
 ("group: why without names", 'f"{len(items)} {_PLURAL.get(e.kind, e.kind)} in {where}: " + ", ".join(i.name for i in items)', 'f"{len(items)} {_PLURAL.get(e.kind, e.kind)} in {where}"'),
 ("label: grouped unit always files", '    unit = "files" if e.path.endswith("/") or e.kind == "version_bump" else _UNIT.get(e.kind, "names")', '    unit = "files"'),
 ("label: version bump unit", ' or e.kind == "version_bump" else', " else"),
 ("label: version bump unlabelled", '"version_bump": "version bump",', ""),
 ("label: whitespace only unlabelled", '\n          "whitespace_only": "whitespace only"}', "}"),
 ("label: agent instructions unlabelled (T37)", '\n          "agent_instructions": "agent instructions",', ""),
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
 ("stub: registry sentence dropped", "thread_stub(e, RG.sentence(registry), other_person,", "thread_stub(e, None, other_person,"),
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
 ("plain_facts: raw name", 'plain = {"kind": e.kind, "name": shown_name(e.name)', 'plain = {"kind": e.kind, "name": e.name'),
]
# T20: the team policy file (itemator/policy.py) and how ci.py uses it, judged by tests/test_policy.py
PC = [
 ("policy: an edit is not an extra", "    if edit:                            # issue describes it", "    if False:                            # issue describes it"),
 ("policy: an edit keeps the stray duplicate", "found = [e for e in found if not e.name == e.path == edit.path] + [edit]", "found = [*found, edit]"),
 ("policy: an edit stays unplaced", "        unplaced = [u for u in unplaced if u != edit.path]\n", ""),
 ("policy: no edit on a no-issue MR (T41)", "edit = policy_edit(files, at)       # T41:", 'edit = policy_edit(files, at) if state != "no_issue" else None       # T41:'),
 ("policy: rename away not seen", 'if POL.FILE in (f["filename"], f.get("previous_filename")):', 'if POL.FILE == f["filename"]:'),
 ("policy: quieting ignored", "        if why:\n            quieted.append", "        if False:\n            quieted.append"),
 ("policy: state not recomputed", '    if state != "no_issue":\n        state = decide_state(', '    if False:\n        state = decide_state('),
 ("policy: read from the MR head", "policy = POL.read(repo_dir, target)", "policy = POL.read(repo_dir, head)"),
 ("names: other person ignored", "other = bool(policy and policy.other_person_required)", "other = False"),
 ("names: other person always", "other = bool(policy and policy.other_person_required)", "other = bool(policy)"),
 ("stub: sentence dropped", 'facts += f" {OTHER_PERSON}" if other_person else ""', 'facts += ""'),
 ("card: notes dropped", 'caveat = " ".join(c for c in (caveat, *notes) if c) or None', "pass"),
 ("card: unused reason dropped", "    if policy.ignored:\n        return f\"The team", "    if False:\n        return f\"The team"),
 ("card: quieted not listed", "    if quieted:\n        n = len(quieted)", "    if False:\n        n = len(quieted)"),
 ("card: every path not said", "    if every:\n", "    if False:\n"),
 ("card: quieted list not capped", "quieted[:_SHOWN_QUIETED]", "quieted"),
 ("json: ignored_extras empty", 'for e, why in quieted]}', 'for e, why in []]}'),
 ("log: quieted list not cut", "        if size() > limit and len(quiet) > 20:          # T20", "        if False:"),
 ("checker: caveat dropped", 'CHECKER_CAVEAT if checker and checker["source"] != "base" else None', "None"),
 ("checker: sha not compared", ' and env.get("ITEMATOR_CHECKER_SHA") == target', ""),
 ("checker: any value means base", 'env.get("ITEMATOR_CHECKER") == "base" and', 'env.get("ITEMATOR_CHECKER") is not None and'),
]
PO = [
 ("schema: unknown table allowed", "        if table not in SCHEMA:\n            return", "        if False:\n            return"),
 ("schema: non-table allowed", "        if not isinstance(value, dict):\n            return", "        if False:\n            return"),
 ("schema: unknown key allowed", "            if want is None:\n", "            if False:\n"),
 ("schema: wrong type allowed", "            if type(v) is not want:", "            if False:"),
 ("schema: default asks for another person", 'names.get("other_person_required", False)', 'names.get("other_person_required", True)'),
 ("kinds: unknown kind allowed", "if type(k) is not str or k not in X.KINDS:", "if type(k) is not str:"),
 ("kinds: built-in exception listable", "        if k in NEVER_IGNORED:\n            return", "        if False:\n            return"),
 ("paths: no pattern cap", "    if len(paths) > MAX_PATTERNS:", "    if False:"),
 ("paths: cap off by one", "    if len(paths) > MAX_PATTERNS:", "    if len(paths) >= MAX_PATTERNS:"),
 ("paths: empty pattern allowed", "if type(p) is not str or not p:", "if type(p) is not str:"),
 ("paths: control characters allowed", "        if _CONTROL.search(p):", "        if False:"),
 ("paths: C1 controls allowed", '_CONTROL = re.compile(r"[\\x00-\\x1f\\x7f-\\x9f]")', '_CONTROL = re.compile(r"[\\x00-\\x1f\\x7f]")'),
 ("paths: no length cap", "        if len(p) > MAX_PATTERN_CHARS:", "        if False:"),
 ("size: not capped in parse", "    if len(data) > MAX_BYTES:\n        return", "    if False:\n        return"),
 ("size: read before the cap", "        if not size.isdigit() or int(size) > MAX_BYTES:", "        if not size.isdigit():"),
 ("size: cap off by one", "int(size) > MAX_BYTES", "int(size) >= MAX_BYTES"),
 ("file: symlink read", 'kind != b"blob" or mode not in (b"100644", b"100755")', 'kind != b"blob"'),
 ("file: missing file not recognised", "        if path != FILE.encode():\n            return Policy(sha=sha)\n", ""),
 ("sha: not checked", "    if not isinstance(sha, str) or not _SHA.fullmatch(sha):", "    if not isinstance(sha, str):"),
 ("sha: search, not fullmatch", "not _SHA.fullmatch(sha)", "not _SHA.search(sha)"),
 ("git: no timeout", "check=False, timeout=TIMEOUT)", "check=False)"),
 ("git: timeout not caught", "    except subprocess.TimeoutExpired as e:\n        raise _Unreadable(f\"git {args[0]} timed out\") from e\n", ""),
 ("registry: not-found package quieted", 'all((p.get("lookup") == "ok" and p.get("found") is True)', 'all((p.get("lookup") == "ok")'),
 ("registry: unread package quieted", '               for p in registry["packages"])', '               or p.get("lookup") == "unavailable" for p in registry["packages"])'),
 ("registry: lookup cap not checked", ' or registry.get("count") != len(registry["packages"])', ""),
 ("registry: exception dropped", '    if e.kind == "new_dependency" and not _registry_knows_every_package(registry):\n        return None\n', ""),
 ("built-in: binary quietable", 'NEVER_IGNORED = ("policy_changed", "binary_or_large_added", "agent_instructions")', 'NEVER_IGNORED = ("policy_changed", "agent_instructions")'),
 ("built-in: policy edit quietable", 'NEVER_IGNORED = ("policy_changed", "binary_or_large_added", "agent_instructions")', 'NEVER_IGNORED = ("binary_or_large_added", "agent_instructions")'),
 ("built-in: agent instructions quietable (T37)", 'NEVER_IGNORED = ("policy_changed", "binary_or_large_added", "agent_instructions")', 'NEVER_IGNORED = ("policy_changed", "binary_or_large_added")'),
 ("paths: one matching file suffices", "    if not all(any(fnmatch.fnmatchcase(f, g) for g in policy.paths) for f in files):", "    if not any(any(fnmatch.fnmatchcase(f, g) for g in policy.paths) for f in files):"),
 ("paths: case-insensitive", "    if not all(any(fnmatch.fnmatchcase(f, g) for g", "    if not all(any(fnmatch.fnmatch(f.lower(), g.lower()) for g"),
 ("paths: rename source ignored", "        if old:\n            out.add(old)\n", "        pass\n"),
 ("paths: group items ignored", "    if items:\n        paths = [i.path for i in items]\n", "    if False:\n        paths = []\n"),
 ("paths: detail files ignored", '    elif e.detail and (e.path.endswith("/") or e.kind == "version_bump"):', "    elif False:"),
 ("every path: not reported", '"ignores_every_path": [p for p in self.paths if matches_everything(p)]', '"ignores_every_path": []'),
 ("reason: backtick kept", '_UNSAFE = re.compile(r"[`\\x00-', '_UNSAFE = re.compile(r"[\\x00-'),
 ("reason: no length cap", "return _UNSAFE.sub(\"'\", str(value))[:40]", "return _UNSAFE.sub(\"'\", str(value))"),
]
# T26: (label, old, new, file, the test file that must kill it)
T26 = [
 ("attrs: text file left binary", '        if not is_binary and any(line.startswith("Binary files ") for line in header):\n', '        if False:\n', "itemator/ci.py", "tests/test_diff_attributes.py"),
 ("attrs: binary by git's word", "        is_binary = any(o in binary for o in pair)\n", '        is_binary = any(line.startswith("Binary files ") for line in header)\n', "itemator/ci.py", "tests/test_diff_attributes.py"),
 ("attrs: blob test skipped", "    binary = _binary_blobs(repo, [o for pair in blobs for o in pair])\n", "    binary = set()\n", "itemator/ci.py", "tests/test_diff_attributes.py"),
 ("attrs: NUL test misses byte 0", 'if b"\\0" in first:', 'if b"\\0" in first[1:]:', "itemator/ci.py", "tests/test_diff_attributes.py"),
 ("attrs: binary keeps a forced patch", "        if is_binary:\n            hunks = None\n", "", "itemator/ci.py", "tests/test_diff_attributes.py"),
 ("attrs: textconv on", '_DIFF = ("--find-renames", "--no-ext-diff", "--no-textconv")', '_DIFF = ("--find-renames", "--no-ext-diff")', "itemator/ci.py", "tests/test_diff_attributes.py"),
 ("attrs: attributes file read", '["git", "-c", "core.attributesFile=/dev/null", "-C", repo, *args]', '["git", "-C", repo, *args]', "itemator/ci.py", "tests/test_diff_attributes.py"),
 ("attrs: system file read", 'env = {**os.environ, "GIT_ATTR_NOSYSTEM": "1", ', 'env = {**os.environ, ', "itemator/ci.py", "tests/test_diff_attributes.py"),
 ("attrs: base attributes not used", "    src = base if ATTR_SOURCE else None\n", "    src = None\n", "itemator/ci.py", "tests/test_diff_attributes.py"),
 ("attrs: re-read without --text", '"--no-color", "--text", "-p"', '"--no-color", "-p"', "itemator/ci.py", "tests/test_diff_attributes.py"),
 ("answers: a manifest is a config file", "    return not _manifest(path) and (\n", "    return (\n", "itemator/ci.py", "tests/test_answers.py"),
 ("answers: any file is a config file", 'name in (".gitlab-ci.yml", "Dockerfile") or name.startswith("Dockerfile.") or name.endswith(_CONFIG_EXT))', "True)", "itemator/ci.py", "tests/test_answers.py"),
 ("answers: dependency outside a manifest", 'if e.kind == "new_dependency" and _manifest(e.path) and (', 'if e.kind == "new_dependency" and (', "itemator/ci.py", "tests/test_answers.py"),
 ("answers: a list without its items", "not e.detail or (items and len(", "not e.detail or (True and len(", "itemator/ci.py", "tests/test_answers.py"),
 ("answers: list not capped", ")) <= MAX_LISTED)):", ")) <= 10 * MAX_LISTED)):", "itemator/ci.py", "tests/test_answers.py"),
 ("answers: cap off by one", ")) <= MAX_LISTED)):", ")) < MAX_LISTED)):", "itemator/ci.py", "tests/test_answers.py"),
 ("answers: modified file removable", '.get("status") == "added":', '.get("status") is not None:', "itemator/ci.py", "tests/test_answers.py"),
 ("answers: a group name removable", "if e.kind in _ADDED_KINDS and e.name == e.path and", "if e.kind in _ADDED_KINDS and", "itemator/ci.py", "tests/test_answers.py"),
 ("answers: tests_removed removable", '_ADDED_KINDS = ("stray_file", "binary_or_large_added", "build_output_added", "agent_instructions")', '_ADDED_KINDS = ("stray_file", "binary_or_large_added", "build_output_added", "agent_instructions", "tests_removed")', "itemator/ci.py", "tests/test_answers.py"),
 ("answers: agent instructions not removable (T37)", '"build_output_added", "agent_instructions")', '"build_output_added")', "itemator/ci.py", "tests/test_answers.py"),
 ("stub: split always offered", '" if "split" in offers else ""', '" if True else ""', "itemator/ci.py", "tests/test_answers.py"),
 ("stub: remove always offered", '" if "remove" in offers else ""', '" if True else ""', "itemator/ci.py", "tests/test_answers.py"),
 ("stub: offers not passed", "other_person, answers(e, items, by_path, always), said, askers),", "other_person, said=said, askers=askers),", "itemator/ci.py", "tests/test_answers.py"),
 ("target: merge base used", "    target, resolved = target_tip(repo_dir, env, base)\n", "    target, resolved = base, True\n", "itemator/ci.py", "tests/test_policy.py"),
 ("target: not a full sha used", "        if _SHA40.fullmatch(sha):\n", "        if sha:\n", "itemator/ci.py", "tests/test_policy.py"),
 ("target: fallback caveat dropped", "             TARGET_CAVEAT if fallback else None,\n", "             None,\n", "itemator/ci.py", "tests/test_policy.py"),
 ("target: fallback says target branch", "    at = AT_FORK if fallback else AT_TARGET\n", "    at = AT_TARGET\n", "itemator/ci.py", "tests/test_policy.py"),
 ("target: policy source kept", '        policy = dataclasses.replace(policy, source="merge_base")\n', "        pass\n", "itemator/ci.py", "tests/test_policy.py"),
 ("checker: compared with the merge base", "checker=checker_of(env, target, head)", "checker=checker_of(env, base, head)", "itemator/ci.py", "tests/test_policy.py"),
 ("card: other-person sentence dropped", "    if asks_other:\n        out.append(ASKS_OTHER)\n", "", "itemator/ci.py", "tests/test_policy.py"),
 ("card: other-person sentence, nothing to name", "asks_other=other and bool(kept)", "asks_other=other", "itemator/ci.py", "tests/test_policy.py"),
 ("parse: deep TOML raises", "    except (RecursionError, MemoryError, OverflowError, ValueError):\n        return TOO_DEEP\n", "    except MemoryError:\n        return TOO_DEEP\n", "itemator/policy.py", "tests/test_policy.py"),
 ("reason: TOML message shown", 'return f"it is not valid TOML ({where})"', "return f\"it is not valid TOML ({_UNSAFE.sub(' ', str(e))[:120]})\"", "itemator/policy.py", "tests/test_policy.py"),
 ("every path: one probe", '_PROBES = ("a", "a/b/c.d", ".x", "-", "Dockerfile")', '_PROBES = ("a/b/c.d",)', "itemator/policy.py", "tests/test_policy.py"),
 ("every path: any probe", "return all(fnmatch.fnmatchcase(p, pattern) for p in _PROBES)", "return any(fnmatch.fnmatchcase(p, pattern) for p in _PROBES)", "itemator/policy.py", "tests/test_policy.py"),
 ("registry: url source quieted", '(p.get("lookup") == "not_from_registry" and p.get("reason") == "own_package")', 'p.get("lookup") == "not_from_registry"', "itemator/policy.py", "tests/test_policy.py"),
 ("registry: not_supported quieted", '               for p in registry["packages"])', '               or p.get("lookup") == "not_supported" for p in registry["packages"])', "itemator/policy.py", "tests/test_policy.py"),
 ("registry: own_package not counted", '               or (p.get("lookup") == "not_from_registry" and p.get("reason") == "own_package")\n', "", "itemator/policy.py", "tests/test_policy.py"),
 ("policy: source not reported", '"source": self.source', '"source": "target_branch"', "itemator/policy.py", "tests/test_policy.py"),
]
# T35 and T38: said or silent (itemator/said.py and its wiring in itemator/ci.py), judged by tests/test_said.py
SD, CI, TS = "itemator/said.py", "itemator/ci.py", "tests/test_said.py"
T35 = [(label, old, new, path, TS) for label, old, new, path in [
 ("said: listed never", "                out.append(LISTED)\n                continue\n", "                out.append(NAMED)\n                continue\n", SD),
 ("said: listed tested on the rest", "if any(_find(k, listed, False, until, clock) for k in keys):", "if any(_find(k, rest, False, until, clock) for k in keys):", SD),
 ("said: weak shown as named", 'out.append(NAMED if found == "strong" else WEAK if found else', "out.append(NAMED if found else", SD),
 ("said: the search stops at a weak match", "found = _find(k, rest, True, until, clock) or found", "found = _find(k, rest, False, until, clock) or found", SD),
 ("said: title ignored", 'listed, rest, hidden = _texts(_cap(title or "")[0].translate(_DROP).replace("\\n", " "), text)', 'listed, rest, hidden = _texts("", text)', SD),
 ("said: cut says silent", "None if (cut or over or unclosed)", "None if (over or unclosed)", SD),
 ("said: over the cap says silent", "None if (cut or over or unclosed)", "None if (cut or unclosed)", SD),
 ("said: unclosed comment says silent", "None if (cut or over or unclosed)", "None if (cut or over)", SD),
 ("said: hidden HTML read", "    if hidden:\n        return [None] * len(extras)\n", "", SD),
 ("said: blank text read", "    if not description or not description.strip():\n", "    if not description:\n", SD),
 ("said: no text says silent", "    if not description or not description.strip():\n        return [None] * len(extras)\n", "    if not description or not description.strip():\n        return [SILENT] * len(extras)\n", SD),
 ("said: weak shown", "    return [None if s == WEAK else s for s in said_detail(title, description, extras, **kw)]", "    return [NAMED if s == WEAK else s for s in said_detail(title, description, extras, **kw)]", SD),
 ("said: deadline not checked per extra", "            if clock() > until:\n                raise _Late\n            keys = _keys(candidates)", "            keys = _keys(candidates)", SD),
 ("match: deadline not checked in the search", "        if clock() > until:\n            raise _Late\n        i = t.low.find", "        i = t.low.find", SD),
 ("match: substring", 'if not _edge_before(t.low, i) or not _edge_after(t.low, i + n) or (base and i and t.low[i - 1] == "/"):', "if False:", SD),
 ("match: joining characters end a name", "return not (_word(c) or (c in _JOIN and j + 1 < len(low) and _word(low[j + 1])))", "return not _word(c)", SD),
 ("match: joining characters start a name", "return not (_word(c) or (c in _JOIN and i >= 2 and _word(low[i - 2])))", "return not _word(c)", SD),
 ("match: a sentence-end dot continues", "(c in _JOIN and j + 1 < len(low) and _word(low[j + 1]))", "c in _JOIN", SD),
 ("match: underscore ends a word", 'return c.isalnum() or c == "_"', "return c.isalnum()", SD),
 ("match: base name after a slash", ' or (base and i and t.low[i - 1] == "/")', "", SD),
 ("strong: code not strong", 'if t.code[i] or "/" in text or', 'if "/" in text or', SD),
 ("strong: a full path not strong", 'if t.code[i] or "/" in text or (not ordinary', "if t.code[i] or (not ordinary", SD),
 ("strong: ordinary words strong", "(not ordinary and t.text[i:i + n] == text)", "(t.text[i:i + n] == text)", SD),
 ("strong: case ignored", "(not ordinary and t.text[i:i + n] == text)", "(not ordinary)", SD),
 ("ordinary: no length limit", "(s.isalpha() and s.islower() and len(s) <= ORDINARY)", "(s.isalpha() and s.islower())", SD),
 ("ordinary: upper case ordinary", "(s.isalpha() and s.islower() and len(s) <= ORDINARY)", "(s.isalpha() and len(s) <= ORDINARY)", SD),
 ("ordinary: generic directories not", "(s.isalpha() and s.islower() and len(s) <= ORDINARY) or _lower(s) in GENERIC)", "(s.isalpha() and s.islower() and len(s) <= ORDINARY))", SD),
 ("keys: short names matched", "if len(s) < MIN_LEN or not any(", "if len(s) < 1 or not any(", SD),
 ("keys: punctuation names matched", "        if len(s) < MIN_LEN or not any(ch.isalnum() for ch in s):\n", "        if len(s) < MIN_LEN:\n", SD),
 ("keys: control characters kept", "        if any(ord(ch) < 32 or 0x7F <= ord(ch) <= 0x9F for ch in text):\n            continue\n", "", SD),
 ("keys: base flag lost", "seen[s] = seen.get(s, True) and base", "seen[s] = False", SD),
 ("keys: a base name hides the full name", "seen[s] = seen.get(s, True) and base", "seen[s] = seen.get(s, False) or base", SD),
 ("names: no base name", "        out += [(full, False), (posixpath.basename(full), True)]\n", "        out += [(full, False)]\n", SD),
 ("names: no items", "    out += [(str(d), False) for d in list(detail)[:MAX_NAMES]]\n", "", SD),
 ("comments: not stripped", '        j = text.find("<!--", search)\n', "        j = -1\n", SD),
 ("comments: stripped inside code spans", "if fenced[ln] or _in(spans[ln], j - starts[ln]):", "if fenced[ln]:", SD),
 ("comments: stripped inside fences", "if fenced[ln] or _in(spans[ln], j - starts[ln]):", "if _in(spans[ln], j - starts[ln]):", SD),
 ("comments: unclosed says read", '            return "".join(out), True\n', '            return "".join(out), False\n', SD),
 ("links: destination and title kept", "out.append(line[i:o - 1] if image else line[i:o] + line[o + 1:j])", "out.append(line[i:k])", SD),
 ("images: alt kept", 'image = o > i and line[o - 1] == "!"', "image = False", SD),
 ("refdefs: kept", "        if _REFDEF.match(line):\n            out.append((\"\", False, False))\n            continue\n", "", SD),
 ("tags: attributes kept", 'out.append((_TAG.sub("", plain), False))', "out.append((plain, False))", SD),
 ("tags: hidden not seen", '            hidden = hidden or "hidden" in low or "style" in low\n', "            hidden = hidden\n", SD),
 ("invisible: kept", "text, unclosed = _uncomment(text.translate(_DROP))", "text, unclosed = _uncomment(text)", SD),
 ("code spans: none", "        spans.append((runs[k][0], runs[m][0] + runs[m][1]))\n", "", SD),
 ("cap: none", 'return raw[:MAX_BYTES].decode("utf-8", "ignore"), len(text) > len(head) or len(raw) > MAX_BYTES', 'return raw.decode("utf-8", "ignore"), False', SD),
 ("cap: in characters only", "len(text) > len(head) or len(raw) > MAX_BYTES", "len(text) > len(head)", SD),
 ("heading: level 7", "if not 1 <= n <= 6 or", "if not 1 <= n <= 7 or", SD),
 ("heading: no space needed", '(len(s) > n and s[n] not in " \\t")', "False", SD),
 ("heading: closing hashes kept", '    if not bare or bare[-1] in " \\t":\n        text = bare.strip()\n', "", SD),
 ("heading: case-sensitive", '.rstrip(":").strip().casefold() == HEADING', '.rstrip(":").strip() == HEADING', SD),
 ("heading: emphasis kept", 'text.strip().strip("*_").strip()', "text.strip()", SD),
 ("section: never ends at a heading", '            here, region, blank = _beyond(heading), "start", True\n', '            here, region, blank = here or _beyond(heading), "start", True\n', SD),
 ("section: a rule does not end it", "        if _rule(line) or (_underline(line) and not blank) or (here and (", "        if (_underline(line) and not blank) or (here and (", SD),
 ("section: a bold line does not end it", '_bold_only(s) or (region != "start" and _label(s))', '(region != "start" and _label(s))', SD),
 ("section: a label does not end it", '_bold_only(s) or (region != "start" and _label(s))', "_bold_only(s)", SD),
 ("section: a first-block label ends it", '(region != "start" and _label(s))', "_label(s)", SD),
 ("section: an HTML block does not end it", "            html, here = True, False\n", "            html = True\n", SD),
 ("html: no HTML blocks", "        if _html_start(line):\n", "        if False:\n", SD),
 ("html: any tag is a block tag", "return name[:k] in _BLOCK_TAGS and", "return bool(name[:k]) and", SD),
 ("fence: ignored", "        f = _fence(line)\n        if f is not None:\n            fence = f\n", "        f = None\n        if f is not None:\n            fence = f\n", SD),
 ("fence: a shorter fence closes", "len(s) >= fence[1] and ", "", SD),
 ("fence: no $$ blocks", '    if s.rstrip() == "$$":\n        return "$", 2\n', "", SD),
 ("setext: none", "if heading is None and blank and _paragraph(line) and k < len(lines) and _underline(lines[k]):", "if False:", SD),
 ("setext: without a blank line before", "if heading is None and blank and _paragraph(line)", "if heading is None and _paragraph(line)", SD),
 ("listed: any paragraph", '            elif region in ("start", "para"):\n', '            elif region in ("start", "para", "after", "other"):\n', SD),
 ("listed: no list continuation", '            elif region == "list" or (region == "gap" and _indent(line) >= 2):\n', "            elif False:\n", SD),
 ("order: none", "    ranked = sorted(zip(said, kept), key=lambda p: p[0] != SAID.SILENT)\n", "    ranked = list(zip(said, kept))\n", CI),
 ("order: silent last", "key=lambda p: p[0] != SAID.SILENT)", "key=lambda p: p[0] == SAID.SILENT)", CI),
 ("stub: said sentence dropped", '    facts += f" {SAID.SENTENCE[said]}" if said else ""\n', "", CI),
 ("stub: sentence after the other-person one", '    facts += f" {SAID.SENTENCE[said]}" if said else ""\n    facts += f" {OTHER_PERSON}" if other_person else ""\n', '    facts += f" {OTHER_PERSON}" if other_person else ""\n    facts += f" {SAID.SENTENCE[said]}" if said else ""\n', CI),
 ("plain_facts: said missing", '    if said:\n        plain["said"] = said\n', "", CI),
 ("facts: cut not passed", "                     cut=description_cut)", "                     cut=False)", CI),
 ("run: the CI variable trusted", '    cut = not mr.get("description") and bool(description)\n', "    cut = False\n", CI),
 ("facts: title not passed", "    said = SAID.said(mr_title, mr_description,", '    said = SAID.said("", mr_description,', CI),
 ("facts: names from the name only", "[SAID.names(e.name, e.path, e.detail) for (e, _), _ in kept]", "[[e.name] for (e, _), _ in kept]", CI),
]]
# T40: the `always` offer (itemator/ci.py, judged by tests/test_answers.py) and the react prompt (judged by
# tests/test_react_prompt.py)
TA, FL, TP = "tests/test_answers.py", "flows/itemator_react.yml", "tests/test_react_prompt.py"
LG, TL = "itemator/decisions.py", "tests/test_decisions.py"
T40 = [(label, old, new, path, test) for label, old, new, path, test in [
 ("always: any kind", 'ALWAYS_KINDS = ("ci_or_config", "stray_file")', 'ALWAYS_KINDS = ("ci_or_config", "stray_file", "tests_removed")', CI, TA),
 ("always: stray files not offered", 'ALWAYS_KINDS = ("ci_or_config", "stray_file")', 'ALWAYS_KINDS = ("ci_or_config",)', CI, TA),
 ("always: never-ignored kind offered", " and e.kind not in POL.NEVER_IGNORED and e.name", " and e.name", CI, TA),
 ("always: a line of a file", " and e.name == e.path and not e.detail\n", " and not e.detail\n", CI, TA),
 ("always: a group by detail", " and not e.detail\n            and not items", "\n            and not items", CI, TA),
 ("always: a group by items", "            and not items and bool(ALWAYS_PATH", "            and bool(ALWAYS_PATH", CI, TA),
 ("always: glob characters allowed", 'ALWAYS_PATH = re.compile(r"[A-Za-z0-9._/@+-]{1,120}")', 'ALWAYS_PATH = re.compile(r"[^\\s`]{1,120}")', CI, TA),
 ("always: 121 characters", 'ALWAYS_PATH = re.compile(r"[A-Za-z0-9._/@+-]{1,120}")', 'ALWAYS_PATH = re.compile(r"[A-Za-z0-9._/@+-]{1,121}")', CI, TA),
 ("always: 119 characters", 'ALWAYS_PATH = re.compile(r"[A-Za-z0-9._/@+-]{1,120}")', 'ALWAYS_PATH = re.compile(r"[A-Za-z0-9._/@+-]{1,119}")', CI, TA),
 ("always: a prefix of the path", "bool(ALWAYS_PATH.fullmatch(e.path))", "bool(ALWAYS_PATH.match(e.path))", CI, TA),
 ("always: manifests offered", " and not _manifest(e.path))\n", ")\n", CI, TA),
 ("always: policy not found", 'policy.get("found") is True and', "True and", CI, TA),
 ("always: ignored policy used", 'policy.get("ignored") is None', "True", CI, TA),
 ("always: merge-base policy used", '                and policy.get("source") == "target_branch"\n', "", CI, TA),
 ("always: no room off by one", "< POL.MAX_PATTERNS)", "<= POL.MAX_PATTERNS)", CI, TA),
 ("always: the flag ignored", "if always and can_always(e, items) else offers", "if can_always(e, items) else offers", CI, TA),
 ("always: offered first", '(*offers, "always")', '("always", *offers)', CI, TA),
 ("always: facts offer it with any policy", "    always = always_allowed(policy.to_dict() if policy else None)       # T40\n", "    always = bool(policy)\n", CI, TA),
 ("always: not passed to the stub", "other_person, answers(e, items, by_path, always), said, askers),", "other_person, answers(e, items, by_path), said, askers),", CI, TA),
 ("stub: always sentence dropped", 'always = f"{ALWAYS} " if "always" in offers else ""', 'always = ""', CI, TA),
 ("stub: always sentence first", 'f"{split}{remove}{always}If this', 'f"{always}{split}{remove}If this', CI, TA),
 ("prompt: refusal list misses remember", '"Remove partly done:", "Cannot remember:" or "Remember failed:" (there may be none).', '"Remove partly done:" or "Cannot remember:" (there may be none).', FL, TP),
 ("prompt: reminder misses remember", '"Remove partly done:", "Cannot remember:" or "Remember failed:"; otherwise', '"Remove partly done:"; otherwise', FL, TP),
 ("prompt: offer sentence differs", "reply `always`; that opens a merge request that changes the team policy.\" the thread is ALWAYS_OK", "reply `always`.\" the thread is ALWAYS_OK", FL, TP),
 ("prompt: no mention step", "        Step 7b. The mention thread.", "        The mention thread.", FL, TP),
 ("prompt: mention reopened", "discussion_id and resolved true. Never touch any other discussion", "discussion_id and resolved false. Never touch any other discussion", FL, TP),
 ("prompt: bot threads resolved", "take every discussion whose first note is not a bot note, whose", "take every discussion whose", FL, TP),
 ("prompt: fork not refused", ' If source_project_id is not project_id, reply "Cannot remember: the branch is in a fork." and stop.', "", FL, TP),
 ("prompt: description not exact", " Close it to keep asking.\" (no other text", "\" (no other text", FL, TP),
 ("prompt: kept reply without kept by", '"Kept: `NAME`, kept by @WHO. Policy change', '"Kept: `NAME`, by @WHO. Policy change', FL, TP),
 ("prompt: whole line rewritten", 'paths = ["a"] becomes paths = ["a", "PATH"]', 'paths = ["a"] becomes paths = ["PATH"]', FL, TP),
 ("prompt: create_merge_request dropped", '      - "create_merge_request"\n', "", FL, TP),
]]
T42 = [(label, old, new, path, test) for label, old, new, path, test in [
 ("t42: comment match allowed", " or OLD does not appear exactly once in the whole decoded file (a comment counts)", "", FL, TP),
 ("t42: trailing comma allowed", " or any entry in the list contains a [ or a ] character, or the list holds a # or ends with a comma", "", FL, TP),
 ("t42: leftover branch ignored", " Otherwise call gitlab_api_get with endpoint \"/api/v4/projects/<project_id>/repository/branches/<BRANCH with each / written as %2F>\"; if that branch exists, reply \"Cannot remember: the branch `BRANCH` is left from an earlier try; delete it, then reply always again.\" and stop (HTTP 404 means go on).", "", FL, TP),
 ("t42: compare endpoint dropped", '"/api/v4/projects/<project_id>/repository/compare" and params {"from": TIP, "to": BRANCH, "straight": "true"}', '"/api/v4/projects/<project_id>/repository/files/.itemator.toml" and params {"ref": BRANCH}', FL, TP),
 ("t42: compare not straight", '"to": BRANCH, "straight": "true"}', '"to": BRANCH}', FL, TP),
 ("t42: two plus lines allowed", 'and exactly one line starting with "+"', 'and a line starting with "+"', FL, TP),
 ("t42: mention typed with the answer", "T1 with every @ai-itemator- mention taken out and spaces at both ends taken off, is exactly NAME", "T1 is exactly NAME", FL, TP),
 ("t42: T2 keeps its spaces", "then spaces at both ends and one trailing full stop taken off again, in lower case", "in lower case", FL, TP),
 ("t42: mention step resolves a person's question", ", and in which every note after the first is a bot note or a system note (no person has replied)", "", FL, TP),
 ("t42: mention step resolves a mention of a person", ' and mentions no @account except accounts whose name starts with "@ai-itemator-"', "", FL, TP),
 ("t42: no-issue label swapped", ' (leave add_labels out while the label "itemator::no-issue" is on: these labels replace each other, and the second one would lift the Draft hold)', "", FL, TP),
 ("t42: always offered where the flow cannot edit", '                and policy.get("paths_line_ok") is True                 # T42: the flow can make the one-line edit\n', "", CI, TA),
 ("t42: paths line seen twice", "return bool(m) and not m.group(1).rstrip().endswith(\",\") and text.count(hits[0]) == 1", "return bool(m) and not m.group(1).rstrip().endswith(\",\")", "itemator/policy.py", "tests/test_policy.py"),
 ("t42: trailing comma allowed", "return bool(m) and not m.group(1).rstrip().endswith(\",\") and text.count", "return bool(m) and text.count", "itemator/policy.py", "tests/test_policy.py"),
 ("t42: two paths lines allowed", "    if len(hits) != 1:\n        return False\n    m = _PATHS_LINE", "    if not hits:\n        return False\n    m = _PATHS_LINE", "itemator/policy.py", "tests/test_policy.py"),
 ("t42: table runs to the end of the file", '        if ln.startswith("["):\n            break\n        table.append(ln)', "        table.append(ln)", "itemator/policy.py", "tests/test_policy.py"),
 ("t42: no [ignore] table needed", "    if start is None:\n        return False\n    table = []", "    if start is None:\n        start = -1\n    table = []", "itemator/policy.py", "tests/test_policy.py"),
 ("t42: brackets inside the list allowed", '_PATHS_LINE = re.compile(r" *paths = \\[([^#\\[\\]\\n]*)\\][^\\n]*")', '_PATHS_LINE = re.compile(r" *paths = \\[([^#\\n]*)\\][^\\n]*")', "itemator/policy.py", "tests/test_policy.py"),
 ("t42: compare check ignores the inserted text", ', and NEW_LINE must be OLD with only \', "PATH"\' or \'"PATH"\' inserted just before the ] that closes the list', "", FL, TP),
 ("t42: a # inside the list allowed", '_PATHS_LINE = re.compile(r" *paths = \\[([^#\\[\\]\\n]*)\\][^\\n]*")', '_PATHS_LINE = re.compile(r" *paths = \\[([^\\n]*)\\][^\\n]*")', "itemator/policy.py", "tests/test_policy.py"),
 ("t42: label added to no-issue merge request", 'or (the label "itemator::no-issue" is not on the merge request and the label "itemator::needs-names" is missing)', 'or the label "itemator::needs-names" is missing', FL, TP),
]]
T43 = [(label, old, new, path, test) for label, old, new, path, test in [
 ("t43: no marker needed", 'if not isinstance(body, str) or not MARKER.search(body):', 'if not isinstance(body, str):', LG, TL),
 ("t43: any author believed", ' or str((n.get("author") or {}).get("username", "")) != REACT_BOT', "", LG, TL),
 ("t43: a name that starts like the account believed", 'str((n.get("author") or {}).get("username", "")) != REACT_BOT', 'not str((n.get("author") or {}).get("username", "")).startswith(REACT_BOT)', LG, TL),
 ("t43: system notes believed", 'if not isinstance(n, dict) or n.get("system") or', "if not isinstance(n, dict) or", LG, TL),
 ("t43: oldest summary wins", 'str(n.get("created_at", "")) >= best[0]', 'str(n.get("created_at", "")) <= best[0]', LG, TL),
 ("t43: everyone is the author", 'by_author=(i["who"] == author)', 'by_author=True', LG, TL),
 ("t43: mentions kept in titles", 'text = re.sub(r"[`<>\\[\\]()!@]", "", text)', 'text = re.sub(r"[`<>\\[\\]()!]", "", text)', LG, TL),
 ("t43: addresses kept in titles", 'text = re.sub(r"(?i)\\b[a-z][a-z0-9+.-]*:(?://|\\\\\\\\)\\S*|\\bwww\\.\\S+", "link removed", text)', 'pass', LG, TL),
 ("t43: backtick kept in names", '.replace("`", "")', "", LG, TL),
 ("t43: release block stacked", 'existing.index(START) < existing.rindex(END)', "True", LG, TL),
 ("t43: the first end marker closes the block", 'existing[existing.rindex(END) + len(END):]', 'existing[existing.index(END) + len(END):]', LG, TL),
 ("t43: window start included", 'lo < t <= hi', 'lo <= t <= hi', LG, TL),
 ("t43: time zones compared as text", 'lo, hi = _utc(since), _utc(until)', 'lo, hi = since, until', LG, TL),
 ("t43: window end excluded", 'lo < t <= hi', 'lo < t < hi', LG, TL),
 ("t43: any host asked", 'if urllib.parse.urlsplit(url).netloc != self.host:', 'if False:', LG, TL),
 ("t43: existing release never updated", "        if isinstance(existing, dict):", "        if False:", LG, TL),
 ("t43: pages never stop", "            if len(data) < 100:\n                break\n", "", LG, TL),
 ("t43: missing release counted", "if not (missing_ok and status == 404):", "if True:", LG, TL),
 ("t43: oldest previous tag", "(older[-1] if older else", "(older[0] if older else", LG, TL),
 ("t43: moved read as kept", '    ("moved", re.compile(r"- " + _NAME + r": moved to', '    ("kept", re.compile(r"- " + _NAME + r": moved to', LG, TL),
 ("t43: report mode writes", 'done = publish(api, a.tag, section) if a.tag else "no release (report mode)"', 'done = publish(api, a.tag or "x", section)', LG, TL),
]]
TH = "tests/test_hold.py"
T44 = [(label, old, new, path, test) for label, old, new, path, test in [
 ("t44: any account's summary counts", "if not n.get(\"system\") and who == REACT_BOT and f", "if not n.get(\"system\") and f", CI, TH),
 ("t44: a name that starts like the account counts", "who == REACT_BOT and f", "who.startswith(REACT_BOT) and f", CI, TH),
 ("t44: a system note counts", "if not n.get(\"system\") and who == REACT_BOT", "if who == REACT_BOT", CI, TH),
 ("t44: any commit's summary counts", 'f"{_NAMED_MARK}{head}" in str(n.get("body", ""))', '_NAMED_MARK in str(n.get("body", ""))', CI, TH),
 ("t44: never blocked", '"blocked": not named, "reason"', '"blocked": False, "reason"', CI, TH),
 ("t44: holds when nothing is beyond the issue", ' or not report["extras"]:', ":", CI, TH),
 ("t44: only the first page", "if named or len(notes) < 100:", "if True:", CI, TH),
 ("t44: unreadable notes pass", '            if not isinstance(notes, list):\n                why = "the notes could not be read"\n                break', '            if not isinstance(notes, list):\n                named = True\n                break', CI, TH),
 ("t44: a held job exits 0", "              f\"{HOLD_LINE}\", file=sys.stderr)\n        return 1", "              f\"{HOLD_LINE}\", file=sys.stderr)\n        return 0", CI, TH),
 ("t44: the card does not say what to do", "        report[\"card\"][\"todo_line\"] = f'{report[\"card\"][\"todo_line\"]} {HOLD_LINE}'", "        pass", CI, TH),
 ("t44: hold on by default", 'names.get("hold_until_named", False)', 'names.get("hold_until_named", True)', "itemator/policy.py", TH),
 ("t44: hold key not in the schema", '"hold_until_named": bool, "asker_required": bool}', '"asker_required": bool}', "itemator/policy.py", TH),
 ("t44: bad value accepted", 'if type(v) is not want:', 'if False:', "itemator/policy.py", TH),
]]
TA45 = "tests/test_asker.py"
T45 = [(label, old, new, path, test) for label, old, new, path, test in [
 ("t45: key on by default", 'names.get("asker_required", False)', 'names.get("asker_required", True)', "itemator/policy.py", TA45),
 ("t45: key not in the schema", '"hold_until_named": bool, "asker_required": bool}', '"hold_until_named": bool}', "itemator/policy.py", TA45),
 ("t45: sentence omitted", '    facts += f" {asker_sentence(askers)}" if askers else ""\n', "", CI, TA45),
 ("t45: sentence added when the key is off", "if policy and policy.asker_required else ()", "if policy else ()", CI, TA45),
 ("t44: another project's issue author named", 'if not str(i.get("ref", "")).startswith("#"):', 'if False:', CI, TA45),
 ("t44: no warning when nobody can keep an extra", "nobody_can=other and bool(askers) and bool(kept) and _author_wrote(issues, mr_author_id)", "nobody_can=False", CI, TA45),
 ("t44: warning also when someone else wrote the issue", "nobody_can=other and bool(askers) and bool(kept) and _author_wrote(issues, mr_author_id)", "nobody_can=other and bool(askers) and bool(kept)", CI, TA45),
 ("t45: invalid username kept", "if isinstance(u, str) and _USERNAME.fullmatch(u) and u not in out:", "if isinstance(u, str) and u not in out:", CI, TA45),
 ("t45: a 4th name kept", "    return out[:MAX_ASKERS]", "    return out[:MAX_ASKERS + 1]", CI, TA45),
 ("t45: restriction claimed with no issue", "asks_asker=bool(askers) and bool(kept)", "asks_asker=bool(policy and policy.asker_required) and bool(kept)", CI, TA45),
 ("t45: author_id used instead of username", '"author_username": author.get("username")}', '"author_username": author.get("id")}', CI, TA45),
 ("t45: sentence before the other-person one", '    facts += f" {OTHER_PERSON}" if other_person else ""\n    facts += f" {asker_sentence(askers)}" if askers else ""\n', '    facts += f" {asker_sentence(askers)}" if askers else ""\n    facts += f" {OTHER_PERSON}" if other_person else ""\n', CI, TA45),
 ("t45: card line never shown", "asks_asker=bool(askers) and bool(kept)", "asks_asker=False", CI, TA45),
 ("t45: plain_facts without the names", '    if askers:\n        plain["asker_usernames"] = list(askers)\n', "", CI, TA45),
 ("t45: a name repeated", "_USERNAME.fullmatch(u) and u not in out:", "_USERNAME.fullmatch(u):", CI, TA45),
]]
T46 = [(label, old, new, path, test) for label, old, new, path, test in [
 ("t46: anyone's name keeps an asker thread", ", and, in an ASKER_ONLY thread, the author's username is exactly one of ASKERS; DISMISSED", "; DISMISSED", FL, TP),
 ("t46: anyone's dismissal counts", "\"not an extra\" and, in an ASKER_ONLY thread, the author's username is exactly one of ASKERS; SPLIT", "\"not an extra\"; SPLIT", FL, TP),
 ("t46: always from any of CREW", "the author is in CREW and, in an ASKER_ONLY thread, the author's username is exactly one of ASKERS, and the reply", "the author is in CREW and the reply", FL, TP),
 ("t46: split needs the asker too", "SPLIT if T2 is exactly \"split\" and T2 is not NAME in lower case and the author is in CREW and", "SPLIT if T2 is exactly \"split\" and T2 is not NAME in lower case and the author is in CREW and, in an ASKER_ONLY thread, the author's username is exactly one of ASKERS, and", FL, TP),
 ("t46: usernames compared without case", "(compared with the same letters and the same case)", "(compared without regard to letter case)", FL, TP),
 ("t46: asker names read loosely", "each copied exactly (same letters, same case).", "each copied (letter case does not matter).", FL, TP),
 ("t44: a planted flag counts again", "If the part of that first note after the backtick that closes NAME contains the text \"Only the person who wrote", "If that first note contains the text \"Only the person who wrote", FL, TP),
 ("t46: no ASKER_ONLY detection", " If the part of that first note after the backtick that closes NAME contains the text \"Only the person who wrote the linked issue (\" the thread is ASKER_ONLY (the team policy lets only the person who wrote the issue keep it): ASKERS = the usernames written as @name between the last place that text appears and the next \") can keep this.\" after it, separated by \" or \", each copied exactly (same letters, same case).", "", FL, TP),
 ("t46: detection text not the checker's", "contains the text \"Only the person who wrote the linked issue (\" the thread", "contains the text \"Only the person who wrote the issue (\" the thread", FL, TP),
 ("t46: first sentence trusted, not the last", "between the last place that text appears and the next", "between the first place that text appears and the next", FL, TP),
 ("t46: unreadable askers do not fail closed", " If any part there is not one @name made only of letters, digits, _, . and -, ASKERS is empty, so no reply can keep or dismiss that extra (split and remove still work).", "", FL, TP),
 ("t46: refusal of others not spelled out", " In an ASKER_ONLY thread a name, \"not an extra\" or \"always\" from anyone whose username is not exactly one of ASKERS (compared with the same letters and the same case) fits no test, even from AUTHOR or someone in CREW: the thread stays open and gets no reply.", "", FL, TP),
 ("t46: reminder never names the asker", "\"Waiting for the person who wrote the issue (@x): \" if some thread of a name in OPEN_NAMES is ASKER_ONLY and its ASKERS is not empty (in place of @x write the first such thread's ASKERS, each with its @, joined with \" or \"), else ", "", FL, TP),
 ("t46: asker reminder ignores refusals", ", in both cases only when no thread of a name in OPEN_NAMES", " and no thread of a name in OPEN_NAMES", FL, TP),
 ("t46: summary never credits the asker", "if some extra thread is ASKER_ONLY, PEOPLE is not empty and every name in it is one of the ASKERS of an ASKER_ONLY thread, a blank line and the line \"All of it was typed by the person who wrote the issue.\"; otherwise, if", "if", FL, TP),
 ("t46: receipt without the idempotence search", " Call gitlab_api_get with endpoint \"/api/v4/projects/<project_id>/search\" and params {\"scope\": \"notes\", \"search\": \"<MARKER_R>\", \"per_page\": \"20\"}. If any entry in its data has noteable_type \"Issue\", noteable_iid equal to ISSUE_IID, and an author whose username is REACT_BOT, post nothing; if the search fails, post nothing.", "", FL, TP),
 ("t46: receipt posted when the search fails", "author whose username is REACT_BOT, post nothing; if the search fails, post nothing.", "author whose username is REACT_BOT, post nothing.", FL, TP),
 ("t46: receipt search looks at MR notes", "If any entry in its data has noteable_type \"Issue\", noteable_iid equal to ISSUE_IID", "If any entry in its data has noteable_type \"MergeRequest\", noteable_iid equal to ISSUE_IID", FL, TP),
 ("t46: receipt marker without the head", "MARKER_R = \"itemator:receipt=<IID>:<HEAD>\"", "MARKER_R = \"itemator:receipt=<IID>\"", FL, TP),
 ("t46: receipt while names are open", "Do this step only when OPEN_NAMES is empty, the merge request has at least one extra", "Do this step only when the merge request has at least one extra", FL, TP),
 ("t46: receipt with no extras", "only when OPEN_NAMES is empty, the merge request has at least one extra (one NAME), and step 7", "only when OPEN_NAMES is empty and step 7", FL, TP),
 ("t46: receipt without the summary", ", and step 7 posted the summary in this run or its search found the summary already there (if that search failed, skip this step).", ".", FL, TP),
 ("t46: create_issue_note dropped", "      - \"create_issue_note\"\n", "", FL, TP),
]]
# T51: the bot approval is gone (GitLab staff: a flow's approval counts as the person who started it). Each mutant puts
# part of it back; the first six add one forbidden word each.
S8 = '<number in OPEN_NAMES> open." No analysis.'
T51 = [(label, old, new, path, test) for label, old, new, path, test in [
 ("t51: /approve posted", S8, S8 + ' Then post one note whose whole body is /approve.', FL, TP),
 ("t51: approval_state read", S8, S8 + ' Read "/api/v4/projects/<project_id>/merge_requests/<IID>/approval_state" first.', FL, TP),
 ("t51: approved_by read", S8, S8 + " Say whether REACT_BOT is in approved_by.", FL, TP),
 ("t51: eligible_approvers read", S8, S8 + " Say whether REACT_BOT is among the eligible_approvers.", FL, TP),
 ("t51: APPROVED field", S8, S8 + " APPROVED is yes or no.", FL, TP),
 ("t51: approve quick action in the slash rule", 'may start with "/", with no exception (GitLab runs such a line as a command).', 'may start with "/" (GitLab runs such a line as a command), except the one note whose whole body is "/approve".', FL, TP),
 ("t51: header lets the flow approve", "you never approve a merge request, you never merge or close one,", "you never merge or close a merge request, you approve one only in step 7d and only by the one note it describes,", FL, TP),
 ("t51: header drops never approve", "you never approve a merge request, you never merge or close one,", "you never merge or close a merge request,", FL, TP),
 ("t51: a Step 7d is back", "        Step 8. Reply with one short line:", "        Step 7d. Approval. Post a note that asks a person to approve.\n\n        Step 8. Reply with one short line:", FL, TP),
 ("t51: Step 8 reports an approval", '<number in OPEN_NAMES> open." No analysis.', '<number in OPEN_NAMES> open, approved <yes|no>." No analysis.', FL, TP),
 # the three T46 mutants of these lines that were not about approving, with their anchors updated (judged by older tests)
 ("t51: no rule against slash lines", ' No line of any note, reply, title or description you write may start with "/", with no exception (GitLab runs such a line as a command).', "", FL, TP),
 ("t51: early stop skips the mention step", "change nothing for this merge request except in step 7b.", "change nothing for this merge request.", FL, TP),
 ("t51: loop stops at 7b", "Do steps 2 to 7c for each IID in MRS", "Do steps 2 to 7b for each IID in MRS", FL, TP),
]]

# T52: the deployment page (itemator/shipped.py). Each mutant breaks one line; tests/test_shipped.py must fail.
SH, SHT = "itemator/shipped.py", "tests/test_shipped.py"
T52 = [(label, old, new, SH, SHT) for label, old, new in [
 ("t52: no escaping of GitLab's text", "    e = html.escape\n", "    e = str\n"),
 ("t52: the window ignores the previous deployment", 'since = (previous or {}).get("created_at") or "1970-01-01T00:00:00Z"', 'since = "1970-01-01T00:00:00Z"'),
 ("t52: an empty GitLab list is not a fallback", "    return mrs or None", "    return mrs if got is not None else None"),
 ("t52: no deployment is shown", "DEPLOYMENTS = 8", "DEPLOYMENTS = 0"),
 ("t52: refused requests are not counted", '"unreadable_requests": api.failures}', '"unreadable_requests": 0}'),
 ("t52: one merge request is plural", "{'' if s['merge_requests'] == 1 else 's'}", "{'s'}"),
 ("t52: no job token still runs", "if not (a.api and a.project and token):", "if False:"),
]]
# T53: the Developer Flow's issue read from its branch name (itemator/ci.py), judged by tests/test_ci.py. Two mutants
# are left out as equivalent: dropping the regex's leading ^ (re.match anchors already) and `if n is not None` -> `if n`
# (an issue numbered 0 does not exist).
T53 = [(label, old, new, "itemator/ci.py", "tests/test_ci.py") for label, old, new in [
 ("t53: the branch issue reported as from the description", 'return [_issue(raw, project_id)], "branch"', 'return [_issue(raw, project_id)], "description"'),
 ("t53: the branch outranks the description", '    if issues:\n        return issues, "description"\n    n = flow', '    if False:\n        return issues, "description"\n    n = flow'),
 ("t53: a missing branch issue is not reported", '        warnings.append(f"#{n} is named in the branch {source_branch} but was not found")\n', ''),
 ("t53: any digits after the kind", 're.compile(r"^duo/[^/]+/(\\d+)-")', 're.compile(r"^duo/[^/]+/(\\d+)")'),
 ("t53: the job does not pass the branch", 'env.get("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME"),', 'env.get("CI_MERGE_REQUEST_SOURCE_BRANCH"),'),
]]
# T54: a branch number is read only when the description names the same issue (itemator/ci.py), judged by tests/test_ci.py.
T54 = [(label, old, new, "itemator/ci.py", "tests/test_ci.py") for label, old, new in [
 ("t54: the description is not checked", "if n is not None and not mentions_issue(description, n, project_path):", "if False:"),
 ("t54: the job does not pass the project path", '                                        env.get("CI_PROJECT_PATH"))', '                                        None)'),
 ("t54: the skipped branch is not reported", '        warnings.append(f"#{n} is named in the branch {source_branch} but not in the description, so it was not read")\n', '        pass\n'),
 ("t54: other/repo#n counts", r'rf"(?<![\w/!#&.-])#{n}(?!\d)"', r'rf"(?<![!#&.-])#{n}(?!\d)"'),
 ("t54: #n matches #n0", r'rf"(?<![\w/!#&.-])#{n}(?!\d)"', r'rf"(?<![\w/!#&.-])#{n}"'),
 ("t54: a merge request URL counts", "/-/(?:issues|work_items)/{n}(?!\\d)", "/-/(?:issues|work_items|merge_requests)/{n}(?!\\d)"),
 ("t54: any project's URL counts", "{re.escape(project_path)}/-/", ".+?/-/"),
 ("t54: the URL's host is not required", r'rf"://[^/\s]+/{re.escape', r'rf"/{re.escape'),
 ("t54: issues/n matches issues/n0", "/-/(?:issues|work_items)/{n}(?!\\d)", "/-/(?:issues|work_items)/{n}"),
 ("t54: no project path still reads URLs", "return bool(project_path) and re.search(", "return bool(project_path) or re.search("),
]]
# T55: scan history (itemator/scan.py), judged by tests/test_scan.py. Not mutated: the team policy read (the tests use none),
# the branch passed to linked_issues (covered by T53/T54 in itemator/ci.py) and the escaping call on an extra's name (_cell is tested).
T55 = [(label, old, new, "itemator/scan.py", "tests/test_scan.py") for label, old, new in [
 ("t55: no first parent", 'f"{commit}^1"', 'f"{commit}"'),
 ("t55: a squash commit is ignored", 'commit = mr.get("merge_commit_sha") or mr.get("squash_commit_sha")', 'commit = mr.get("merge_commit_sha")'),
 ("t55: a fast-forward merge gets the clone reason", '    if not (mr.get("merge_commit_sha") or mr.get("squash_commit_sha")):\n        return', '    if False:\n        return'),
 ("t55: listed by update time", "&order_by=merged_at&sort=desc", "&order_by=updated_at&sort=desc"),
 ("t55: pipes not escaped", '"""Text for a markdown table cell: a pipe would start a new cell."""\n    return str(text)', '"""Text for a markdown table cell: a pipe would start a new cell."""\n    return str(text)\n    return str(text)'),
 ("t55: the title is not escaped", "{_cell(r['title'])}", "{r['title']}"),
 ("t55: --last 0 is accepted", "    if a.last < 1:\n", "    if False:\n"),
 ("t55: oldest first", "reverse=True)[:last]", ")[:last]"),
 ("t55: --last ignored", "reverse=True)[:last]", "reverse=True)"),
 ("t55: unmerged rows kept", 'isinstance(m.get("iid"), int) and m.get("merged_at")]', 'isinstance(m.get("iid"), int)]'),
 ("t55: one page only", "        if len(data) < 100:\n            break\n    return sorted", "        break\n    return sorted"),
 ("t55: unreadable counted as read", 'read = [r for r in rows if r["state"] != "unreadable"]', "read = list(rows)"),
 ("t55: no issue counted as linked", 'linked = [r for r in read if r["state"] != "no_issue"]', "linked = read"),
 ("t55: a failed read stops the scan", '    except ci.JobError as e:\n        return {**row, "state": "unreadable", "reason": str(e)[:200]}', '    except ValueError as e:\n        return {**row, "state": "unreadable", "reason": str(e)[:200]}'),
 ("t55: the page lists merge requests without extras", 'flagged = [r for r in report["merge_requests"] if r.get("extras")]', 'flagged = [r for r in report["merge_requests"] if r["state"] != "unreadable"]'),
 ("t55: a list error exits 0", '        print(f"itemator scan: {e}", file=sys.stderr)\n        return 2', '        print(f"itemator scan: {e}", file=sys.stderr)\n        return 0'),
 ("t55: the branch name is not quoted", "urllib.parse.quote(target, safe='')", "target"),
]]
SRC = {"itemator/ci.py": (REPO / "itemator/ci.py").read_text(), "itemator/registry.py": (REPO / "itemator/registry.py").read_text(),
       "itemator/policy.py": (REPO / "itemator/policy.py").read_text(), "itemator/said.py": (REPO / "itemator/said.py").read_text(), LG: (REPO / LG).read_text(),
       FL: (REPO / FL).read_text(), "itemator/shipped.py": (REPO / "itemator/shipped.py").read_text(),
       "itemator/scan.py": (REPO / "itemator/scan.py").read_text()}
JOBS = ([(*m, "itemator/ci.py", "tests/test_ci.py") for m in M] + [(*m, "itemator/ci.py", "tests/test_ci_anchors.py") for m in A]
        + [(*m, "itemator/ci.py", "tests/test_registry.py") for m in RC] + [(*m, "itemator/registry.py", "tests/test_registry.py") for m in RG]
        + [(*m, "itemator/ci.py", "tests/test_policy.py") for m in PC] + [(*m, "itemator/policy.py", "tests/test_policy.py") for m in PO]
        + T26 + T35 + T40 + T42 + T43 + T44 + T45 + T46 + T51 + T52 + T53 + T54 + T55)
for label, old, new, path, _ in JOBS:
    assert SRC[path].count(old) == 1, f"mutant {label!r}: anchor found {SRC[path].count(old)} times in {path}"
if sys.argv[3:] == ["T17"]:
    JOBS = [j for j in JOBS if j[4] == "tests/test_registry.py"]
if sys.argv[3:] == ["T35"]:
    JOBS = [j for j in JOBS if j[4] == "tests/test_said.py"]
if sys.argv[3:] == ["T40"]:
    JOBS = [j for j in JOBS if j in T40]
if sys.argv[3:] == ["T42"]:
    JOBS = [j for j in JOBS if j in T42]
if sys.argv[3:] == ["T43"]:
    JOBS = [j for j in JOBS if j in T43]
if sys.argv[3:] == ["T44"]:
    JOBS = [j for j in JOBS if j in T44]
if sys.argv[3:] == ["T45"]:
    JOBS = [j for j in JOBS if j in T45]
if sys.argv[3:] == ["T46"]:
    JOBS = [j for j in JOBS if j in T46]
if sys.argv[3:] == ["T51"]:
    JOBS = [j for j in JOBS if j in T51]
if sys.argv[3:] == ["T52"]:
    JOBS = [j for j in JOBS if j in T52]
if sys.argv[3:] == ["T53"]:
    JOBS = [j for j in JOBS if j in T53]
if sys.argv[3:] == ["T54"]:
    JOBS = [j for j in JOBS if j in T54]
if sys.argv[3:] == ["T55"]:
    JOBS = [j for j in JOBS if j in T55]
def run(i, path, text, tests):
    d = WORK / f"m{i:02d}"
    if d.exists(): shutil.rmtree(d)
    for sub in ("itemator", "tests", "tools", "flows"):        # T40: the react prompt is judged too
        shutil.copytree(REPO / sub, d / sub, ignore=shutil.ignore_patterns("__pycache__"))
    (d / path).write_text(text)
    return subprocess.run([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", tests], cwd=d, capture_output=True,
                          text=True)       # T38: -x, one failure kills a mutant; the suite must fit a 10-minute foreground run
for target in sorted({j[4] for j in JOBS}):
    base = run(99, "itemator/ci.py", SRC["itemator/ci.py"], target)
    if base.returncode != 0:
        print(f"the unmutated copy fails {target}, so no mutant can be judged:\n" + base.stdout[-2000:]); sys.exit(2)
survivors = 0
for i, (label, old, new, path, target) in enumerate(JOBS):
    mutated = SRC[path].replace(old, new)
    if path.endswith(".py"):
        try:
            compile(mutated, path, "exec")
        except SyntaxError as e:            # a mutant that does not compile is not "killed by a test": it is a bad mutant
            print(f"INVALID  {label:46s} {e.msg}"); survivors += 1; continue
    r = run(i, path, mutated, target)
    failed = [l.split("::")[1].split(" ")[0] for l in r.stdout.splitlines() if l.startswith("FAILED")]
    killed = r.returncode != 0
    survivors += not killed
    print(f"{'KILLED ' if killed else 'SURVIVED'} {label:46s} {','.join(failed)[:150]}")
total = len(JOBS)
print(f"{total - survivors}/{total} mutants killed")
sys.exit(1 if survivors else 0)
