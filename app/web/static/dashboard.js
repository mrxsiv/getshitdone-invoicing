/* Dashboard trend chart: a dual-axis line chart drawn as inline SVG.
   Three "worms": Sales (ex GST, $ left axis), Labour (ex GST, $ left axis),
   and Invoice volume (count, right axis). Theme colours come from CSS. */
(function () {
  "use strict";

  var el = document.getElementById("trendChart");
  if (!el) return;
  var data = JSON.parse(document.getElementById("trendData").textContent);
  if (!data.length) { el.innerHTML = '<div class="empty">No data yet.</div>'; return; }

  var W = 1000, H = 340, mL = 74, mR = 60, mT = 18, mB = 46;
  var pw = W - mL - mR, ph = H - mT - mB, n = data.length;

  function xs(i) { return mL + (n === 1 ? pw / 2 : pw * i / (n - 1)); }

  function niceMax(v) {
    if (v <= 0) return 1;
    var p = Math.pow(10, Math.floor(Math.log10(v))), f = v / p;
    var nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
    return nf * p;
  }
  function moneyShort(v) {
    if (v >= 1000) return "$" + (v / 1000).toFixed(v >= 10000 ? 0 : 1) + "k";
    return "$" + Math.round(v);
  }
  function moneyFull(v) {
    return Number(v).toLocaleString("en-NZ", { style: "currency", currency: "NZD" });
  }

  var maxMoney = 0, maxVol = 0;
  data.forEach(function (d) {
    maxMoney = Math.max(maxMoney, d.sales, d.labour);
    maxVol = Math.max(maxVol, d.volume);
  });
  var leftMax = niceMax(maxMoney), rightMax = niceMax(maxVol);
  function yL(v) { return mT + ph - ph * v / leftMax; }
  function yR(v) { return mT + ph - ph * v / rightMax; }

  var ticks = 5, parts = [];
  for (var t = 0; t <= ticks; t++) {
    var yy = mT + ph * t / ticks;
    parts.push('<line class="grid" x1="' + mL + '" y1="' + yy + '" x2="' + (W - mR) + '" y2="' + yy + '"/>');
    var lv = leftMax * (ticks - t) / ticks, rv = rightMax * (ticks - t) / ticks;
    parts.push('<text class="axis" x="' + (mL - 8) + '" y="' + (yy + 4) + '" text-anchor="end">' + moneyShort(lv) + "</text>");
    parts.push('<text class="axis" x="' + (W - mR + 8) + '" y="' + (yy + 4) + '" text-anchor="start">' + Math.round(rv) + "</text>");
  }

  function line(key, scale, cls) {
    var d = "";
    data.forEach(function (pt, i) { d += (i ? "L" : "M") + xs(i).toFixed(1) + " " + scale(pt[key]).toFixed(1) + " "; });
    return '<path class="worm ' + cls + '" d="' + d + '"/>';
  }
  function dots(key, scale, cls, fmt) {
    return data.map(function (pt, i) {
      return '<circle class="dot ' + cls + '" cx="' + xs(i).toFixed(1) + '" cy="' + scale(pt[key]).toFixed(1) + '" r="3.5">' +
        "<title>" + pt.label + " " + pt.year + ": " + fmt(pt[key]) + "</title></circle>";
    }).join("");
  }

  data.forEach(function (pt, i) {
    parts.push('<text class="axis" x="' + xs(i).toFixed(1) + '" y="' + (H - mB + 20) + '" text-anchor="middle">' + pt.label + "</text>");
    if (i === 0 || pt.label === "Jan") {
      parts.push('<text class="axis-year" x="' + xs(i).toFixed(1) + '" y="' + (H - mB + 34) + '" text-anchor="middle">' + pt.year + "</text>");
    }
  });

  parts.push('<text class="axis-title" x="' + (mL - 8) + '" y="' + (mT - 5) + '" text-anchor="end">$</text>');
  parts.push('<text class="axis-title" x="' + (W - mR + 8) + '" y="' + (mT - 5) + '" text-anchor="start">No.</text>');
  parts.push(line("sales", yL, "worm-sales"));
  parts.push(line("labour", yL, "worm-labour"));
  parts.push(line("volume", yR, "worm-volume"));
  parts.push(dots("sales", yL, "dot-sales", moneyFull));
  parts.push(dots("labour", yL, "dot-labour", moneyFull));
  parts.push(dots("volume", yR, "dot-volume", function (v) { return v + (v === 1 ? " invoice" : " invoices"); }));

  el.innerHTML = '<svg viewBox="0 0 ' + W + " " + H + '" class="trend-svg" preserveAspectRatio="xMidYMid meet">' + parts.join("") + "</svg>";
})();
