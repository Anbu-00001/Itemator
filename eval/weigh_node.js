// Runs web/weigh.js under node with the network, for eval/weigh_agreement.py. usage: node eval/weigh_node.js '[{"eco","name","version"}]'
"use strict";
const W = require("../web/weigh.js");
const get = W.browserGet((u, o) => fetch(u, { ...o, headers: { "User-Agent": "itemator-weigh-agreement" } }));
(async () => {
  const out = [];
  for (const p of JSON.parse(process.argv[2])) out.push(await W.weigh(get, p.eco, p.name, p.version));
  process.stdout.write(JSON.stringify(out));
})();
