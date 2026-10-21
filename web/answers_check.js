// The answer log's chain, checked in the visitor's browser the way `python -m itemator.answerlog --verify` checks it: each entry's
// SHA-256 is taken over the hash before it plus the entry without its `prev` and `hash`, written as Python's
// json.dumps(sort_keys=True, separators=(",", ":")) writes it (every character outside printable ASCII as \uXXXX).
// tests/test_answers_check.py runs this file under node against the Python version. No library; `digest` is passed in.
"use strict";

const START = "0".repeat(64);
const SHORT = { '"': '\\"', "\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f" };

function str(s) {
  let out = '"';
  for (const c of s) {
    if (SHORT[c]) { out += SHORT[c]; continue; }
    const code = c.charCodeAt(0);
    if (c.length === 1 && code >= 0x20 && code <= 0x7e) { out += c; continue; }
    for (let i = 0; i < c.length; i++) out += "\\u" + c.charCodeAt(i).toString(16).padStart(4, "0");
  }
  return out + '"';
}

function canonical(v) {
  if (v === null) return "null";
  if (v === true) return "true";
  if (v === false) return "false";
  if (typeof v === "string") return str(v);
  if (typeof v === "number") {
    if (!Number.isInteger(v)) throw new Error("only whole numbers are written the same way in both languages");
    return String(v);
  }
  if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]";
  const keys = Object.keys(v).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  return "{" + keys.map((k) => str(k) + ":" + canonical(v[k])).join(",") + "}";
}

function content(entry) {
  const out = {};
  for (const k of Object.keys(entry)) if (k !== "prev" && k !== "hash") out[k] = entry[k];
  return out;
}

// The index of the first entry whose link or hash does not hold, or null when the whole chain holds.
async function verify(entries, digest) {
  let prev = START;
  for (let i = 0; i < entries.length; i++) {
    const e = entries[i];
    if (!e || typeof e !== "object" || e.prev !== prev || e.hash !== (await digest(prev + canonical(content(e))))) return i;
    prev = e.hash;
  }
  return null;
}

async function browserDigest(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function check(say, shownHead) {
  say("Checking…");
  let log;
  try {
    const r = await fetch("answers.json", { cache: "no-store" });
    log = await r.json();
  } catch (err) {
    say("Could not read answers.json: " + err.message);
    return;
  }
  const entries = log.entries || [];
  const bad = await verify(entries, browserDigest);
  if (bad !== null) {
    say(`The chain breaks at entry ${bad + 1} of ${entries.length}.`);
    return;
  }
  const head = entries.length ? entries[entries.length - 1].hash : START;
  say(head === shownHead && head === log.head
    ? `All ${entries.length} entries hold, recomputed in your browser, and the newest hash is the one printed above.`
    : `All ${entries.length} entries hold, but the newest hash is not the one printed above.`);
}

if (typeof document !== "undefined") {
  const button = document.getElementById("check");
  if (button) {
    const out = document.getElementById("checked");
    button.addEventListener("click", () => check((t) => { out.textContent = t; }, button.dataset.head));
  }
}

if (typeof module !== "undefined") module.exports = { canonical, verify, START };
