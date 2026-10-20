// What a PyPI or npm dependency brings along on a fresh install, measured in the browser the way itemator/weight.py measures it in
// the CI job: deps.dev's resolved graph, then each package's download size from its own registry (PyPI: the file pip would most
// likely take on a Linux x86_64 runner with CPython 3.12; npm: the tarball's length, read from the answer's headers and the
// download stopped there). eval/weigh_agreement.py compares the two on real packages. No library; `fetch` is passed in.
"use strict";

const DEPS_DEV = "https://api.deps.dev/v3/systems/";
const SYSTEM = { PyPI: "pypi", npm: "npm" };
const MAX_NODES = 200;
const WORKERS = 8;
const PY_TAG = /-(?:py3|py2\.py3)-none-any\.whl$/;
const CP312 = /-cp312-(?:cp312|abi3)-manylinux[^/]*x86_64[^/]*\.whl$/;
const ABI3 = /-cp3\d+-abi3-manylinux[^/]*x86_64[^/]*\.whl$/;
const PY_LINUX = /-(?:py3|py2\.py3)-none-manylinux[^/]*x86_64[^/]*\.whl$/;

function q(text) {          // Python's urllib.parse.quote(text, safe="")
  return encodeURIComponent(text).replace(/[!'()*]/g, (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase());
}

function pep503(name) {
  return name.toLowerCase().replace(/[-_.]+/g, "-");
}

function graphUrl(eco, name, version) {
  return `${DEPS_DEV}${SYSTEM[eco]}/packages/${q(name)}/versions/${q(version)}:dependencies`;
}

function pickWheel(files) {
  files = (files || []).filter((f) => f && typeof f.filename === "string" && Number.isInteger(f.size));
  const tests = [(n) => CP312.test(n), (n) => ABI3.test(n), (n) => PY_LINUX.test(n), (n) => PY_TAG.test(n),
                 (n) => n.endsWith(".tar.gz") || n.endsWith(".zip")];
  for (const t of tests) {
    const hit = files.filter((f) => t(f.filename) && !f.yanked);
    if (hit.length) return hit.reduce((a, b) => (b.size < a.size ? b : a));
  }
  return null;
}

function nodesOf(doc) {
  const out = [];
  for (const n of (doc && doc.nodes) || []) {
    const key = n && n.versionKey;
    if (!key || typeof key !== "object" || n.bundled) continue;
    if (typeof key.name === "string" && typeof key.version === "string" && key.name && key.version)
      out.push({ name: key.name, version: key.version, relation: n.relation });
  }
  return out;
}

function sizeUrl(eco, name, version) {
  if (eco === "PyPI") return `https://pypi.org/pypi/${q(name)}/${q(version)}/json`;
  const base = name.split("/").pop();
  return `https://registry.npmjs.org/${name}/-/${q(base)}-${q(version)}.tgz`;
}

// get(url, wantLength) -> {status, json} or, with wantLength, {status, length}
async function sizeOf(get, eco, node) {
  try {
    if (eco === "PyPI") {
      const r = await get(sizeUrl(eco, node.name, node.version), false);
      if (r.status !== 200) return null;
      const f = pickWheel((r.json || {}).urls);
      return f ? f.size : null;
    }
    const r = await get(sizeUrl(eco, node.name, node.version), true);
    return r.status === 200 && Number.isInteger(r.length) && r.length >= 0 ? r.length : null;
  } catch (e) {
    return null;
  }
}

async function weigh(get, eco, name, version) {
  if (!(eco in SYSTEM)) return { weight: "not_supported" };
  if (!version) return { weight: "no_version" };
  const r = await get(graphUrl(eco, eco === "PyPI" ? pep503(name) : name, version), false);
  if (r.status !== 200) return { weight: "unavailable", reason: `graph_http_${r.status}` };
  const doc = r.json || {};
  if (doc.error) return { weight: "unavailable", reason: "graph_error" };
  const nodes = nodesOf(doc);
  if (!nodes.length) return { weight: "unavailable", reason: "empty_graph" };
  const sized = nodes.slice(0, MAX_NODES);
  const sizes = new Array(sized.length);
  let next = 0;
  async function worker() {
    while (next < sized.length) {
      const i = next++;
      sizes[i] = await sizeOf(get, eco, sized[i]);
    }
  }
  await Promise.all(Array.from({ length: Math.min(WORKERS, sized.length) }, worker));
  const known = sized.map((n, i) => [n, sizes[i]]).filter((x) => x[1] !== null);
  const largest = known.slice().sort((a, b) => b[1] - a[1]).slice(0, 5);
  return { weight: "ok", source: "deps.dev", version, packages: nodes.length,
           direct: nodes.filter((n) => n.relation === "DIRECT").length, sized: known.length, of: sized.length,
           bytes: known.reduce((s, x) => s + x[1], 0), capped: nodes.length > MAX_NODES,
           largest: largest.map(([n, s]) => ({ name: n.name, version: n.version, bytes: s })) };
}

function halfUp(x, digits) {      // the same arithmetic as weight.py's _half_up
  const k = Math.pow(10, digits || 0);
  return Math.floor(x * k + 0.5) / k;
}

function human(n) {
  if (n < 1e6) return `${Math.max(1, halfUp(n / 1000))} kB`;
  if (n < 1e9) { const mb = n / 1e6; return mb < 10 ? `${halfUp(mb, 1).toFixed(1)} MB` : `${halfUp(mb)} MB`; }
  const gb = n / 1e9;
  return gb < 10 ? `${halfUp(gb, 1).toFixed(1)} GB` : `${halfUp(gb)} GB`;
}

// The browser's `get`: JSON for graphs and PyPI; for an npm tarball only the Content-Length header, then the download is stopped.
function browserGet(fetchFn) {
  return async (url, wantLength) => {
    const ctl = new AbortController();
    const r = await fetchFn(url, { signal: ctl.signal, credentials: "omit", referrerPolicy: "no-referrer" });
    if (wantLength) {
      const len = r.headers.get("content-length");
      ctl.abort();
      return { status: r.status, length: len === null ? null : Number(len) };
    }
    return { status: r.status, json: r.status === 200 ? await r.json() : null };
  };
}

async function latest(get, eco, name) {
  if (eco === "PyPI") {
    const r = await get(`https://pypi.org/pypi/${q(name)}/json`, false);
    return r.status === 200 ? ((r.json || {}).info || {}).version || null : null;
  }
  const r = await get(`https://registry.npmjs.org/${name.startsWith("@") ? "@" + q(name.slice(1)) : q(name)}/latest`, false);
  return r.status === 200 ? (r.json || {}).version || null : null;
}

if (typeof module !== "undefined") module.exports = { weigh, pickWheel, nodesOf, graphUrl, sizeUrl, human, pep503, q, latest, browserGet };
