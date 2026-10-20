// Node driver for eval/green_agreement.py: node eval/green_node.js deps_rule.js units.json out.json
// Each unit is {id, issue, files}; the answer is what DepsRule.extras lists.
"use strict";
var fs = require("fs");
var D = require(require("path").resolve(process.argv[2]));
var out = {};
JSON.parse(fs.readFileSync(process.argv[3], "utf8")).forEach(function (u) { out[u.id] = D.extras(u.issue, u.files); });
fs.writeFileSync(process.argv[4], JSON.stringify(out));
