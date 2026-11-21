/* SpotFit 최종 대시보드 계산 규칙. 화면 없이 node에서도 불러 Python 결과와 대조한다 (test_final.py).
 * 출처: 김지영/step4_dashboard/views.py (composite · order_rows), 김지영/step4_dashboard/mbti.py (검사 채점 · 유형 맞추기 · S/G 가중치).
 */
(function (root) {
  "use strict";

  var KEYS = ["sales", "competition", "stability", "demand"];
  var COLS = { sales: "sa", competition: "co", stability: "st", demand: "de" };
  var WEIGHT_NAMES = { sales: "매출 잠재력", competition: "경쟁", stability: "안정성", demand: "수요" };
  var MATCH = "일치", NEAR = "경계 유형", OTHER = "다른 유형", UNKNOWN = "판정 불가";

  /* 자료가 있는 영역끼리 가중치를 다시 나눈 가중 평균. 가중치 합이 0이면 null. */
  function composite(scores, weights) {
    var num = 0, den = 0, used = 0;
    for (var k = 0; k < KEYS.length; k++) {
      var key = KEYS[k], w = Number(weights[key] || 0), s = scores[key];
      if (s !== null && s !== undefined && w > 0) {
        num += s * w;
        den += w;
        used += 1;
      }
    }
    return { total: den > 0 ? num / den : null, used: used };
  }

  /* 고른 업종의 점수 대상 칸과 현재 가중치의 종합 점수. 점수는 서울 전체 같은 업종 기준이다. */
  function industryRows(payload, code, weights) {
    var s = payload.scores[code];
    if (!s) return [];
    var rows = [];
    for (var j = 0; j < s.a.length; j++) {
      var r = {
        i: s.a[j], code: payload.areas.code[s.a[j]],
        sales: s.sa[j], competition: s.co[j], stability: s.st[j], demand: s.de[j],
        stores: s.n[j], opens: s.op[j], closes: s.cs[j], salesMonth: s.sm[j], comp: s.cp[j], close: s.cl[j],
        pf: s.pf[j], pw: s.pw[j], pr: s.pr[j], salesNote: payload.salesNotes[s.sn[j]],
      };
      var c = composite(r, weights);
      r.total = c.total;
      r.used = c.used;
      rows.push(r);
    }
    return rows;
  }

  /* 종합 점수가 높은 순. 같으면 점포가 많은 순, 그다음 상권코드 순. 종합 점수가 없으면 뒤로. */
  function rankRows(rows) {
    return rows.slice().sort(function (a, b) {
      var an = a.total === null, bn = b.total === null;
      if (an !== bn) return an ? 1 : -1;
      if (!an && a.total !== b.total) return b.total - a.total;
      if (a.stores !== b.stores) return b.stores - a.stores;
      return a.code < b.code ? -1 : a.code > b.code ? 1 : 0;
    });
  }

  function median(values) {
    var v = values.filter(function (x) { return x !== null && x !== undefined && !isNaN(x); }).sort(function (a, b) { return a - b; });
    if (!v.length) return null;
    var m = v.length >> 1;
    return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
  }

  /* 평균 순위 (동점은 평균). pandas rank() 기본값과 같다. */
  function ranks(values) {
    var idx = values.map(function (v, i) { return i; }).sort(function (a, b) { return values[a] - values[b]; });
    var out = new Array(values.length);
    for (var i = 0; i < idx.length;) {
      var j = i;
      while (j + 1 < idx.length && values[idx[j + 1]] === values[idx[i]]) j++;
      var r = (i + j) / 2 + 1;
      for (var k = i; k <= j; k++) out[idx[k]] = r;
      i = j + 1;
    }
    return out;
  }

  function pearson(x, y) {
    var n = x.length, mx = 0, my = 0;
    for (var i = 0; i < n; i++) { mx += x[i]; my += y[i]; }
    mx /= n; my /= n;
    var sxy = 0, sxx = 0, syy = 0;
    for (var j = 0; j < n; j++) {
      var dx = x[j] - mx, dy = y[j] - my;
      sxy += dx * dy; sxx += dx * dx; syy += dy * dy;
    }
    if (sxx === 0 || syy === 0) return null;
    return sxy / Math.sqrt(sxx * syy);
  }

  /* 두 값이 모두 있는 점만 쓴 순위상관. 3점 미만이면 null. build_final.spearman과 같은 규칙. */
  function spearman(x, y) {
    var xs = [], ys = [];
    for (var i = 0; i < x.length; i++) {
      if (x[i] !== null && y[i] !== null && x[i] !== undefined && y[i] !== undefined) { xs.push(x[i]); ys.push(y[i]); }
    }
    if (xs.length < 3) return null;
    return pearson(ranks(xs), ranks(ys));
  }

  /* 기준마다 5문항 중 3개 이상 고른 쪽이 그 글자. 5:0·4:1은 뚜렷, 3:2는 경계. 한 문항이라도 비면 그 기준은 글자가 없다. */
  function scoreAnswers(answers, questions, axes) {
    var out = [];
    axes.forEach(function (ax) {
      var left = ax["왼쪽"], right = ax["오른쪽"];
      var rows = questions.filter(function (q) { return q["기준"] === ax["기준"]; });
      var picked = [];
      rows.forEach(function (q) {
        var a = answers[q["번호"]];
        if (a === "A" || a === "B") picked.push(q[a + " 글자"]);
      });
      var nl = picked.filter(function (c) { return c === left; }).length;
      var nr = picked.filter(function (c) { return c === right; }).length;
      var done = picked.length === rows.length;
      var counts = {};
      counts[left] = nl;
      counts[right] = nr;
      var clear = done && Math.max(nl, nr) >= 4;
      out.push({ axis: ax["기준"], left: left, right: right, letter: done ? (nl > nr ? left : right) : null, counts: counts,
                 answered: picked.length, total: rows.length, clear: clear, boundary: done && !clear });
    });
    var complete = out.every(function (a) { return a.letter; });
    return { source: "검사 결과", complete: complete, answered: out.reduce(function (s, a) { return s + a.answered; }, 0),
             total: questions.length, type: complete ? out.map(function (a) { return a.letter; }).join("") : null, axes: out };
  }

  /* 유형을 직접 고른 경우. 검사 점수가 없으므로 모든 글자를 뚜렷으로 본다. */
  function directResult(code, axes) {
    return { source: "직접 고르기", complete: true, answered: 0, total: 0, type: code,
             axes: axes.map(function (ax, i) {
               return { axis: ax["기준"], left: ax["왼쪽"], right: ax["오른쪽"], letter: code[i], counts: null, answered: 0, total: 0, clear: true, boundary: false };
             }) };
  }

  /* 상권 유형(L/V·E/P 두 글자) → 일치 / 경계 유형. 경계(3:2) 글자는 반대 글자 유형도 경계 유형으로 넣는다. 한 글자씩만 바꾼다. */
  function matchedTypes(result) {
    var code = result.type, two = code.slice(0, 2), out = {};
    out[two] = MATCH;
    for (var i = 0; i < 2; i++) {
      var a = result.axes[i];
      if (a.boundary) {
        var flipped = code[i] === a.left ? a.right : a.left;
        var near = two.slice(0, i) + flipped + two.slice(i + 1);
        if (!(near in out)) out[near] = NEAR;
      }
    }
    return out;
  }

  /* 창업자 S/G → STEP 4 영역 가중치. 3:2 경계이면 STEP 4 기본값 행('경계'). */
  function sgWeights(result, table) {
    var sg = result.axes[2], key = sg.boundary ? "경계" : sg.letter, row = null;
    table.forEach(function (r) { if (r["구분"] === key) row = r; });
    var w = {};
    KEYS.forEach(function (k) { w[k] = Number(row[WEIGHT_NAMES[k]]); });
    return { weights: w, label: row["이름"], key: key };
  }

  function matchLabel(type2, matched) {
    if (type2 === null || type2 === undefined) return UNKNOWN;
    return (matched && matched[type2]) || OTHER;
  }

  /* 예: 'V 4:1 · P 3:2 (경계) · G 5:0'. 직접 고른 경우는 글자만. */
  function axisText(result) {
    if (result.source === "직접 고르기") return result.axes.map(function (a) { return a.letter; }).join(" · ") + " (직접 고름, 검사 점수 없음)";
    return result.axes.map(function (a) {
      if (!a.letter) return a.axis + " " + a.answered + "/" + a.total + "문항";
      var other = a.letter === a.left ? a.right : a.left;
      return a.letter + " " + a.counts[a.letter] + ":" + a.counts[other] + (a.boundary ? " (경계)" : "");
    }).join(" · ");
  }

  /* 시각화 7: 창업자 유형 8개마다 두 글자가 같은 상권만 남기고 S/G 가중치 종합 점수 상위 n곳. */
  function typeCompare(payload, code, weightTable, n) {
    var out = {};
    ["LE", "LP", "VE", "VP"].forEach(function (two) {
      ["S", "G"].forEach(function (sg) {
        var w = sgWeights({ axes: [null, null, { boundary: false, letter: sg }] }, weightTable).weights;
        var rows = industryRows(payload, code, w).filter(function (r) { return payload.areas.type2[r.i] === two && r.total !== null; });
        out[two + sg] = { pool: rows.length, top: rankRows(rows).slice(0, n) };
      });
    });
    return out;
  }

  var api = {
    KEYS: KEYS, COLS: COLS, WEIGHT_NAMES: WEIGHT_NAMES, MATCH: MATCH, NEAR: NEAR, OTHER: OTHER, UNKNOWN: UNKNOWN,
    composite: composite, industryRows: industryRows, rankRows: rankRows, median: median, ranks: ranks, spearman: spearman,
    scoreAnswers: scoreAnswers, directResult: directResult, matchedTypes: matchedTypes, sgWeights: sgWeights,
    matchLabel: matchLabel, axisText: axisText, typeCompare: typeCompare,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SpotfitCore = api;
})(this);
