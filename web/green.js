// The arithmetic of web/green.html: what the unasked dependencies of a change cost on every fresh install, in megabytes and as an
// SCI delta in grams CO2e. perInstall is eval/sci_estimate.py's per_install line for line; the coefficients come from
// results/sci_estimate_v1.json at build time, so the page cannot use other numbers than the results file does.
"use strict";
var Green = (function () {
  function perInstall(c, mb, seconds) {
    var gb = mb / 1000;
    var runnerW = [c.vcpu * c.vcpu_w[0] * c.pue, (c.vcpu * c.vcpu_w[1] + c.mem_gb * c.mem_w_per_gb) * c.pue];
    var out = {};
    [["low", 0], ["high", 1]].forEach(function (e) {
      var i = e[1];
      var net = gb * c.network_kwh_per_gb[i];
      var run = runnerW[i] * seconds[i] / 3600 / 1000;
      var o = (net + run) * c.grid_g_per_kwh[i];
      var m = c.embodied_total_g * (seconds[i] / c.life_s) * (c.vcpu / c.host_vcpu);
      out[e[0]] = { network_kwh: net, runner_kwh: run, operational_g: o, embodied_g: m, sci_g_per_install: o + m };
    });
    return out;
  }

  // weighed: [{bytes, at_least}] for each unasked dependency that was weighed. Install seconds are the studies' medians for
  // one added line, so n lines count n times those seconds.
  function total(c, seconds, weighed, runs) {
    var bytes = 0, least = false, low = 0, high = 0;
    weighed.forEach(function (w) {
      var g = perInstall(c, w.bytes / 1e6, seconds);
      bytes += w.bytes; least = least || w.at_least;
      low += g.low.sci_g_per_install; high += g.high.sci_g_per_install;
    });
    var r = { lines: weighed.length, bytes: bytes, at_least: least, g_low: low, g_high: high };
    if (runs > 0) { r.runs = runs; r.month_bytes = bytes * runs; r.month_g_low = low * runs; r.month_g_high = high * runs; }
    return r;
  }

  function grams(g) {              // three significant figures, in g under a kilogram
    if (g >= 1000) return Number((g / 1000).toPrecision(3)).toString() + " kg";
    return Number(g.toPrecision(g < 1 ? 2 : 3)).toString() + " g";
  }

  return { perInstall: perInstall, total: total, grams: grams };
})();
if (typeof module !== "undefined" && module.exports) module.exports = Green;
