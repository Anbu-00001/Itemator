// Node driver for eval/try_agreement.py: node web/try_agree.js units.json out.json
// Each unit is {id, files} (file rows) or {id, diff} (raw git diff text, read with the page's own diff reader).
"use strict";
var fs = require("fs");
var I = require("./try_checks.js");
var units = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
var out = {};
units.forEach(function (u) {
  var files = u.diff !== undefined ? I.parseDiff(u.diff) : u.files;
  var r = I.run(files);
  if (u.diff !== undefined) r.files = files;
  out[u.id] = r;
});
fs.writeFileSync(process.argv[3], JSON.stringify(out));
