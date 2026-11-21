/* SpotFit 최종 대시보드 화면. 계산 규칙은 core.js(SpotfitCore)에 있고, 데이터는 build_final.py가 넣은 payload다. */
(function () {
  "use strict";
  // 데이터(payload)는 보통 HTML 안에 있다. 비어 있으면(claude.ai 게시본) 같은 폴더의 payload.json을 읽는다.
  const holder = document.getElementById("payload");
  const raw = holder ? holder.textContent.trim() : "";
  if (raw) start(JSON.parse(raw));
  else {
    fetch("payload.json")
      .then((r) => { if (!r.ok) throw new Error(`${r.status} ${r.statusText}`); return r.json(); })
      .then(start)
      .catch((e) => {
        const m = document.getElementById("main");
        if (m) m.insertAdjacentHTML("afterbegin", `<p class="empty">데이터(payload.json)를 불러오지 못했습니다. 페이지를 새로 고쳐 보세요. (${String(e.message).replace(/</g, "&lt;")})</p>`);
      });
  }

  function start(P) {
    const C = window.SpotfitCore;
    document.documentElement.lang = "ko";
    const A = P.areas, NA = A.code.length;
    const IND = Object.fromEntries(P.industries.map((r) => [r.code, r]));
    const KEYS = C.KEYS;
    const SHORT = { sales: "매출", competition: "경쟁", stability: "안정성", demand: "수요" };
    const LONG = C.WEIGHT_NAMES;
    const GROUPS = ["외식", "서비스", "소매"];
    const TYPE_ORDER = ["LES", "LEG", "LPS", "LPG", "VES", "VEG", "VPS", "VPG"];
    const TYPES = Object.fromEntries(P.step5.types.map((r) => [r["유형"], r]));
    const QUESTIONS = P.step5.questions.slice().sort((a, b) => a["화면 순서"] - b["화면 순서"]);
    const DS_ORDER = ["S01", "S02", "K01", "K02", "K03", "K04", "K05", "K06", "K07"];
    const PAGES = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10"];

    // ------------------------------------------------------------ 상태 (브라우저 저장소는 업종 · 테마 편의용으로만)
    const store = {
      get(k) { try { return window.localStorage.getItem("spotfit6:" + k); } catch (e) { return null; } },
      set(k, v) { try { window.localStorage.setItem("spotfit6:" + k, v); } catch (e) { /* 저장 못 해도 화면은 동작 */ } },
    };
    const savedIndustry = store.get("industry");
    const state = {
      industry: savedIndustry && IND[savedIndustry] ? savedIndustry : P.defaultIndustry,
      weights: Object.assign({}, P.defaultWeights), profile: null, selected: null, compare: null,
      answers: {}, mode: "survey", pick: null, rankLimit: 15, rankQuery: "", onlyMatch: false,
      v1: "industry", v2: "area", v5: "type", colDs: "K01", colOnlyStd: true, featLevel: "전체", featAvail: "전체", featQuery: "",
      theme: store.get("theme") || "auto", page: "s1",
    };

    // ------------------------------------------------------------ 도움 함수
    const $ = (id) => document.getElementById(id);
    const esc = (s) => String(s === null || s === undefined ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const isNum = (v) => v !== null && v !== undefined && !Number.isNaN(v);
    const nf = (v, d) => {
      const k = typeof d === "number" ? d : 0; // table()의 f로 넘기면 두 번째 인자가 행이라 무시한다
      return isNum(v) ? Number(v).toLocaleString("ko-KR", { minimumFractionDigits: k, maximumFractionDigits: k }) : "자료 없음";
    };
    const s1f = (v) => (isNum(v) ? v.toFixed(1) : "—");
    const man = (won) => (isNum(won) ? nf(won / 1e4) + "만 원" : "자료 없음");
    const tok = (name) => getComputedStyle(document.documentElement).getPropertyValue("--" + name).trim();
    const seq = () => [1, 2, 3, 4, 5].map((i) => tok("seq" + i));
    const cat = () => [1, 2, 3, 4, 5].map((i) => tok("s" + i));
    const areaLabel = (i) => `${A.name[i]} (${A.gu[i]})`;
    /* 순차 색 위 글자색: 상대 휘도로 검정 · 흰색 중 대비가 큰 쪽 (범주색은 팔레트 규칙대로 흰색, 노랑만 검정) */
    function onFill(hex) {
      const h = String(hex).replace("#", "");
      if (h.length !== 6) return "#0b0b0b";
      const lum = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)));
      return 0.2126 * lum[0] + 0.7152 * lum[1] + 0.0722 * lum[2] > 0.179 ? "#0b0b0b" : "#ffffff";
    }
    const pct = (v, d = 1) => (isNum(v) ? v.toFixed(d) + "%" : "자료 없음");

    function table(cols, rows, opts = {}) {
      let h = `<table class="data"><thead><tr>${cols.map((c) => `<th${c.num ? ' class="num"' : ""} scope="col">${esc(c.l)}</th>`).join("")}</tr></thead><tbody>`;
      rows.forEach((r, idx) => {
        h += `<tr${opts.rowAttr ? opts.rowAttr(r, idx) : ""}>` + cols.map((c) => {
          const v = typeof c.k === "function" ? c.k(r, idx) : r[c.k];
          const cell = c.html ? c.html(v, r) : esc(c.f ? c.f(v, r) : v);
          const cls = [c.num ? "num" : "", c.cls || ""].filter(Boolean).join(" ");
          return `<td${cls ? ` class="${cls}"` : ""}>${cell}</td>`;
        }).join("") + "</tr>";
      });
      if (!rows.length) h += `<tr><td colspan="${cols.length}" class="dim">표시할 행이 없습니다.</td></tr>`;
      return h + "</tbody></table>";
    }
    const autoTable = (records) => table(Object.keys(records[0]).map((k) => ({ k: k, l: k })), records);

    function niceTicks(d0, d1, n = 5) {
      const span = d1 - d0;
      if (span <= 0) return [d0];
      let step = Math.pow(10, Math.floor(Math.log10(span / n)));
      const err = span / n / step;
      if (err >= 7.5) step *= 10; else if (err >= 3.5) step *= 5; else if (err >= 1.5) step *= 2;
      const out = [];
      for (let v = Math.ceil(d0 / step) * step; v <= d1 + step * 1e-9; v += step) out.push(Number(v.toFixed(10)));
      return out;
    }
    function logTicks(d0, d1) {
      const out = [];
      for (let e = Math.floor(Math.log10(d0)); e <= Math.ceil(Math.log10(d1)); e++) {
        [1, 2, 5].forEach((m) => { const v = m * Math.pow(10, e); if (v >= d0 && v <= d1) out.push(v); });
      }
      return out;
    }
    const lin = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0 || 1)) * (r1 - r0);
    const logs = (d0, d1, r0, r1) => (v) => r0 + ((Math.log10(v) - Math.log10(d0)) / (Math.log10(d1) - Math.log10(d0) || 1)) * (r1 - r0);
    const wonTick = (v) => (v >= 1e8 ? nf(v / 1e8, v % 1e8 ? 1 : 0) + "억" : nf(v / 1e4) + "만");

    // ------------------------------------------------------------ 툴팁 (마우스와 키보드 초점 모두)
    const tip = $("tip");
    function showTip(text, x, y) {
      tip.textContent = text;
      tip.hidden = false;
      const r = tip.getBoundingClientRect();
      let left = x + 14, top = y + 14;
      if (left + r.width > window.innerWidth - 8) left = x - r.width - 14;
      if (top + r.height > window.innerHeight - 8) top = y - r.height - 14;
      tip.style.left = Math.max(8, left) + "px";
      tip.style.top = Math.max(8, top) + "px";
    }
    const hideTip = () => { tip.hidden = true; };
    function tipText(t) {
      const own = t.getAttribute("data-tip");
      if (own !== null) return own;
      const host = t.closest("[data-tiphost]");
      return host && host._tip ? host._tip(t.getAttribute("data-ti")) : null;
    }
    document.addEventListener("pointermove", (e) => {
      if (e.target.closest && e.target.closest("[data-owntip]")) return;
      const t = e.target.closest ? e.target.closest("[data-tip],[data-ti]") : null;
      const text = t ? tipText(t) : null;
      if (text) showTip(text, e.clientX, e.clientY); else hideTip();
    });
    document.addEventListener("focusin", (e) => {
      const t = e.target.closest ? e.target.closest("[data-tip],[data-ti]") : null;
      const text = t ? tipText(t) : null;
      if (text) { const r = t.getBoundingClientRect(); showTip(text, r.left + r.width / 2, r.bottom); } else hideTip();
    });
    document.addEventListener("focusout", hideTip);
    window.addEventListener("scroll", hideTip, { passive: true });

    // ------------------------------------------------------------ 지도 (상권 경계 SVG)
    function drawMap(host, o) {
      const m = P.map;
      let s = `<svg viewBox="0 0 ${m.w} ${m.h}" role="img" aria-label="${esc(o.label)}"><path d="${m.grid}" fill="${tok("dot")}"/>`;
      for (let i = 0; i < NA; i++) s += `<path class="a" data-ti="${i}" d="${A.path[i]}" fill="${o.fill(i)}"/>`;
      const surface = tok("surface"), cw = host.clientWidth || 540, ls = Math.min(30, Math.max(13, (10.5 * m.w) / cw)).toFixed(1);
      m.labels.forEach((l) => {
        s += `<text x="${l[0]}" y="${l[1]}" text-anchor="middle" style="font-size:${ls}px;fill:${tok("ink2")};paint-order:stroke;stroke:${surface};stroke-width:4px;pointer-events:none">${esc(l[2])}</text>`;
      });
      (o.outline || []).forEach((i) => { s += `<path d="${A.path[i]}" fill="none" stroke="${tok("ink")}" stroke-width="2.4" pointer-events="none"/>`; });
      host.innerHTML = s + "</svg>";
      host.setAttribute("data-tiphost", "");
      host._tip = (i) => o.tip(Number(i));
      host.onclick = o.click ? (e) => { const p = e.target.closest("[data-ti]"); if (p) o.click(Number(p.getAttribute("data-ti"))); } : null;
    }
    const bin5 = (v) => (v >= 80 ? 4 : v >= 60 ? 3 : v >= 40 ? 2 : v >= 20 ? 1 : 0);
    function rampLegend(labels, extra) {
      const s = seq();
      return `<span>${labels[0]}</span><span class="ramp">${s.map((c, k) => `<i style="background:${c}" data-tip="${esc(labels[k + 2] || "")}"></i>`).join("")}</span><span>${labels[1]}</span>` +
        (labels.length > 2 ? `<span class="note-inline">구간 ${esc(labels.slice(2).join(" · "))}</span>` : "") +
        (extra || []).map(([c, t]) => `<span><span class="sw" style="background:${c}"></span>${esc(t)}</span>`).join("");
    }

    // ------------------------------------------------------------ 점수 행 (업종 · 가중치가 같으면 다시 계산하지 않음)
    let cache = { key: null };
    function scoreRows(weights) {
      const w = weights || state.weights;
      const key = state.industry + JSON.stringify(w);
      if (cache.key === key) return cache;
      const rows = C.rankRows(C.industryRows(P, state.industry, w));
      rows.forEach((r, k) => { r.rank = r.total === null ? null : k + 1; });
      const med = {};
      KEYS.forEach((k) => { med[k] = C.median(rows.map((r) => r[k])); });
      ["salesMonth", "comp", "close", "pf", "pw", "pr", "stores"].forEach((k) => { med[k] = C.median(rows.map((r) => r[k])); });
      cache = { key: key, rows: rows, by: new Map(rows.map((r) => [r.i, r])), med: med, ranked: rows.filter((r) => r.total !== null).length };
      return cache;
    }
    function storeMap(code) {
      const c = P.cells[code], m = new Map();
      if (c) c[0].forEach((a, k) => m.set(a, c[1][k] / 10));
      return m;
    }
    const weightText = (w) => {
      const t = KEYS.reduce((s, k) => s + Number(w[k] || 0), 0);
      return t > 0 ? KEYS.map((k) => `${SHORT[k]} ${Math.round((w[k] / t) * 100)}%`).join(" · ") : "가중치가 모두 0이라 종합 점수를 계산하지 않습니다.";
    };
    const typeText = (i) => (A.type2[i] ? A.type2[i] : "판정 불가");

    // ------------------------------------------------------------ 금융 MBTI
    function surveyResult() { return C.scoreAnswers(state.answers, P.step5.questions, P.step5.axes); }
    function makeProfile(result) {
      const info = TYPES[result.type], w = C.sgWeights(result, P.step5.weights);
      return { type: result.type, info: info, result: result, text: C.axisText(result), matched: C.matchedTypes(result), weights: w.weights, weightLabel: w.label };
    }
    function pendingProfile() {
      if (state.mode === "survey") { const r = surveyResult(); return r.complete ? makeProfile(r) : null; }
      return state.pick ? makeProfile(C.directResult(state.pick, P.step5.axes)) : null;
    }
    function applyProfile(p) {
      state.profile = p;
      state.weights = p ? Object.assign({}, p.weights) : Object.assign({}, P.defaultWeights);
      state.onlyMatch = !!p;
      updateHeader();
      refresh();
    }

    // ------------------------------------------------------------ 머리
    const industryTag = (r) => (!r.scored ? " · 점수 없음" : !r.salesSupplied ? " · 매출 자료 없음" : !r.salesScored ? " · 매출 비교 상권 부족" : "");
    function initHeader() {
      const sel = $("industry");
      sel.innerHTML = GROUPS.map((g) => `<optgroup label="${g}">` + P.industries.filter((r) => r.group === g)
        .map((r) => `<option value="${r.code}">${esc(r.name + industryTag(r))}</option>`).join("") + "</optgroup>").join("");
      sel.value = state.industry;
      sel.addEventListener("change", () => {
        state.industry = sel.value; store.set("industry", sel.value);
        state.selected = null; state.compare = null; state.rankLimit = 15;
        updateHeader(); refresh();
      });
      $("profileChip").addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) applyProfile(null); });
      $("themeBtn").addEventListener("click", () => {
        state.theme = { auto: "light", light: "dark", dark: "auto" }[state.theme];
        store.set("theme", state.theme); applyTheme(); refresh();
      });
      $("versionNote").textContent = `${P.version} · 2025년 1~4분기`;
      applyTheme();
      updateHeader();
    }
    function applyTheme() {
      if (state.theme === "auto") document.documentElement.removeAttribute("data-theme");
      else document.documentElement.setAttribute("data-theme", state.theme);
      $("themeBtn").textContent = "테마: " + { auto: "자동", light: "밝게", dark: "어둡게" }[state.theme];
    }
    function updateHeader() {
      const r = IND[state.industry];
      $("industryNote").textContent = r.scored ? `점수 대상 ${nf(r.cells)}곳` : "점수 없음 (사유는 6장)";
      const p = state.profile;
      $("profileChip").innerHTML = p
        ? `<span class="chip">금융 MBTI <b>${p.type}</b> ${esc(p.info["이름"])} · ${esc(p.weightLabel)}<button type="button" data-clear aria-label="금융 MBTI 적용 해제">✕</button></span>`
        : `<a class="chip off" href="#s7">금융 MBTI 적용 안 함</a>`;
    }

    // ------------------------------------------------------------ 1. 요약
    function fillKeys() {
      const ctx = { kpi: P.kpi, docs: P.docs, step6: { leadOverHalf: P.viz.heat.area.leadShare.filter((v) => v > 50).length } };
      document.querySelectorAll("[data-k]").forEach((el) => {
        const v = el.getAttribute("data-k").split(".").reduce((o, k) => (o === null || o === undefined ? o : o[k]), ctx);
        el.textContent = typeof v === "number" ? (Number.isInteger(v) ? nf(v) : nf(v, 2)) : String(v);
      });
    }
    function renderS1() {
      const k = P.kpi, supplied = P.industries.filter((r) => r.salesSupplied).length;
      const tiles = [
        [nf(k.areas), "곳", "비교 상권", `관광특구 ${k.tourist}곳 제외`],
        [nf(k.industries), "개", "서울 서비스 업종", `매출 제공 ${supplied}개`],
        [nf(k.scoredCells), "칸", "점수 대상 (상권×업종)", `${k.scoredIndustries}개 업종`],
        [nf(k.salesCells), "칸", "매출 잠재력 점수", `${k.salesIndustries}개 업종`],
        [nf(k.type2Areas), "곳", "금융 MBTI 유형 판정 상권", "L/V · E/P 두 글자 모두"],
        [nf(k.semasStores), "개", "상가업소 (상가정보)", "2025-12-31 스냅숏"],
      ];
      $("kpiTiles").innerHTML = tiles.map((t) => `<div class="tile"><div class="v">${t[0]}<small>${t[1]}</small></div><div class="k">${t[2]}</div><div class="s">${t[3]}</div></div>`).join("");
    }

    // ------------------------------------------------------------ 2 · 3. 데이터셋 · 컬럼
    function renderS2() {
      $("datasetTable").innerHTML = table([
        { k: "id", l: "ID" }, { k: "name", l: "데이터셋" }, { k: "provider", l: "제공" }, { k: "format", l: "형식" },
        { k: "rows", l: "행 수", num: true, f: nf }, { k: "cols", l: "열 수", num: true, f: nf }, { k: "period", l: "자료 기간" },
        { k: "vintage", l: "실제 값 시점" }, { k: "role", l: "이번 분석에서 쓴 곳" },
        { k: "url", l: "링크", html: (v) => `<a href="${esc(v)}" target="_blank" rel="noopener">열기 ↗</a>` },
      ], P.docs.datasets);
    }
    function renderS3() {
      const seg = $("colDatasets");
      seg.innerHTML = DS_ORDER.map((d) => `<button type="button" role="tab" data-ds="${d}" aria-selected="${d === state.colDs}">${d}</button>`).join("");
      seg.onclick = (e) => { const b = e.target.closest("[data-ds]"); if (b) { state.colDs = b.getAttribute("data-ds"); renderS3(); } };
      const cb = $("colOnlyStd");
      cb.checked = state.colOnlyStd;
      cb.onchange = () => { state.colOnlyStd = cb.checked; renderS3(); };
      const all = P.docs.columns.filter((r) => r[0] === state.colDs), std = all.filter((r) => r[8]);
      const ds = P.docs.datasets.find((d) => d.id === state.colDs);
      $("colSummary").textContent = `${ds.id} ${ds.name}: 컬럼 ${all.length}개 중 표준 컬럼으로 옮긴 것 ${std.length}개`;
      $("columnTable").innerHTML = table([
        { k: (r) => r[1], l: "순서", num: true }, { k: (r) => r[2], l: "원본 컬럼" }, { k: (r) => r[3], l: "의미" }, { k: (r) => r[4], l: "단위" },
        { k: (r) => r[5], l: "결측률", num: true, f: (v) => v.toFixed(2) + "%" }, { k: (r) => r[6], l: "고유값 수", num: true, f: nf },
        { k: (r) => r[7], l: "예시" }, { k: (r) => r[8], l: "표준 컬럼 (STEP 2)", html: (v) => (v ? `<code>${esc(v)}</code>` : '<span class="dim">—</span>') },
      ], state.colOnlyStd ? std : all);
    }

    // ------------------------------------------------------------ 4. 전처리 · 결합 구조
    function renderS4() {
      const T = Object.fromEntries(P.docs.tables.map((t) => [t.table, t]));
      const B = {
        K01: [0, 10, "K01 추정매출"], K02: [0, 54, "K02 점포"], K03: [0, 98, "K03 상권 영역"], K04: [0, 142, "K04 유동인구"], K05: [0, 186, "K05 집객시설"],
        K06: [0, 230, "K06 직장인구"], K07: [0, 274, "K07 상주인구"], S01: [0, 318, "S01 상가정보"], S02: [0, 362, "S02 업종코드"],
        fact: [230, 20, "fact_trdar_industry_quarter", T.fact_trdar_industry_quarter], dim: [230, 98, "dim_trdar", T.dim_trdar],
        ctx: [230, 196, "trdar_quarter_context", T.trdar_quarter_context], bridge: [230, 318, "semas_spatial_bridge", T.semas_spatial_bridge],
        annual: [520, 20, "annual_features", T.annual_features], s4: [520, 118, "STEP 4 점수표"], s5: [520, 216, "STEP 5 상권 유형"],
        semas: [520, 318, "semas_q4_industry_counts", T.semas_q4_industry_counts], fin: [790, 150, "최종 대시보드"],
      };
      const W = { 0: 150, 230: 220, 520: 210, 790: 170 };
      const H = (k) => (B[k][0] === 0 ? 34 : B[k][0] === 790 ? 70 : 52);
      const sub = { s4: "4개 영역 · 20,522칸", s5: "L/V · E/P · 1,644곳", fin: "STEP 6 시각화 7종" };
      const edges = [["K01", "fact", "1:1 왼쪽 결합"], ["K02", "fact"], ["K03", "dim"], ["dim", "fact", "N:1"], ["K04", "ctx"], ["K05", "ctx"], ["K06", "ctx"], ["K07", "ctx"],
        ["dim", "ctx"], ["S01", "bridge", "within"], ["S02", "bridge"], ["fact", "annual"], ["annual", "s4"], ["ctx", "s4"], ["fact", "s5", "객단가"], ["ctx", "s5"],
        ["bridge", "semas"], ["s4", "fin"], ["s5", "fin"], ["ctx", "fin", "집객시설"]];
      const ax = tok("axis"), ink = tok("ink"), ink2 = tok("ink2"), surf = tok("surface"), s2 = tok("surface-2"), acc = tok("s1");
      let s = `<svg viewBox="0 0 964 410"><defs><marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0L8,4L0,8z" fill="${ax}"/></marker></defs>`;
      edges.forEach(([a, b, lab]) => {
        const [x1, y1] = B[a], [x2, y2] = B[b];
        const sx = x1 + W[x1], sy = y1 + H(a) / 2, tx = x2, ty = y2 + H(b) / 2;
        const same = x1 === x2;
        const d = same ? `M${x1 + W[x1] - 30},${y1 + H(a)}L${x2 + W[x2] - 30},${y2}` : `M${sx},${sy}C${sx + 36},${sy} ${tx - 36},${ty} ${tx - 2},${ty}`;
        s += `<path d="${d}" fill="none" stroke="${ax}" stroke-width="1.3" marker-end="url(#arr)"/>`;
        if (lab) s += `<text x="${same ? x1 + W[x1] - 26 : (sx + tx) / 2}" y="${same ? (y1 + H(a) + y2) / 2 + 4 : (sy + ty) / 2 - 4}" style="font-size:10px;fill:${ink2}" text-anchor="${same ? "start" : "middle"}">${esc(lab)}</text>`;
      });
      Object.keys(B).forEach((k) => {
        const [x, y, name, t] = B[k], w = W[x], h = H(k), src = x === 0, fin = k === "fin";
        s += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="8" fill="${fin ? acc : src ? s2 : surf}" stroke="${fin ? acc : ax}"/>`;
        const c = fin ? "#ffffff" : ink;
        s += `<text x="${x + 10}" y="${y + (src ? 22 : 21)}" style="font-size:${src ? 12 : 12.5}px;font-weight:${src ? 500 : 650};fill:${c}">${esc(name)}</text>`;
        const line2 = t ? `${nf(t.rows)}행 · 키 ${t.key}` : sub[k];
        if (line2 && !src) s += `<text x="${x + 10}" y="${y + 39}" style="font-size:10.5px;fill:${fin ? "#ffffff" : ink2}">${esc(line2.length > 34 ? line2.slice(0, 33) + "…" : line2)}</text>`;
      });
      $("pipeline").innerHTML = s + "</svg>";
      $("tableRows").innerHTML = table([
        { k: "table", l: "표", html: (v) => `<code>${esc(v)}</code>` }, { k: "rows", l: "행 수", num: true, f: nf }, { k: "cols", l: "열 수", num: true, f: nf },
        { k: "key", l: "키", html: (v) => `<code>${esc(v)}</code>` }, { k: "desc", l: "내용" },
      ], P.docs.tables);
    }

    // ------------------------------------------------------------ 5. 파생변수
    function renderS5() {
      const rows = P.docs.features;
      const levels = ["전체"].concat([...new Set(rows.map((r) => r[1]))]);
      const avail = ["전체", "산출", "보류", "STEP 4 · 5"];
      const kind = (r) => (r[7].indexOf("STEP") >= 0 ? "STEP 4 · 5" : r[7]);
      const seg = (host, list, cur, key) => {
        host.innerHTML = list.map((v) => `<button type="button" aria-pressed="${v === cur}" data-v="${esc(v)}">${esc(v)}</button>`).join("");
        host.onclick = (e) => { const b = e.target.closest("[data-v]"); if (b) { state[key] = b.getAttribute("data-v"); renderS5(); } };
      };
      seg($("featLevels"), levels, state.featLevel, "featLevel");
      seg($("featAvail"), avail, state.featAvail, "featAvail");
      const q = $("featQuery");
      q.value = state.featQuery;
      q.oninput = () => { state.featQuery = q.value; drawFeatures(); };
      drawFeatures();
      function drawFeatures() {
        const query = state.featQuery.trim().toLowerCase();
        const shown = rows.filter((r) => (state.featLevel === "전체" || r[1] === state.featLevel) && (state.featAvail === "전체" || kind(r) === state.featAvail)
          && (!query || r.join(" ").toLowerCase().indexOf(query) >= 0));
        $("featSummary").textContent = `${rows.length}개 중 ${shown.length}개 표시 (산출 ${rows.filter((r) => r[7] === "산출").length} · 보류 ${rows.filter((r) => r[7] === "보류").length} · STEP 4 · 5 추가 ${rows.filter((r) => kind(r) === "STEP 4 · 5").length})`;
        $("featureTable").innerHTML = table([
          { k: (r) => r[0], l: "변수", html: (v) => `<code>${esc(v)}</code>` }, { k: (r) => r[1], l: "단위" }, { k: (r) => r[2], l: "계산 공식" }, { k: (r) => r[3], l: "값 단위" },
          { k: (r) => r[4], l: "원본" }, { k: (r) => r[5], l: "분석 목적" }, { k: (r) => r[6], l: "해석" },
          { k: (r) => r[7], l: "확보", html: (v) => (v === "보류" ? '<span class="status none">○ 보류</span>' : `<span class="status done">● ${esc(v)}</span>`) },
        ], shown);
      }
    }

    // ------------------------------------------------------------ 6. 점수 모델
    function renderS6() {
      $("scoreDesign").innerHTML = autoTable(P.step4.design);
      const sliders = $("weightSliders");
      sliders.innerHTML = KEYS.map((k) => `<div class="slider"><label for="w_${k}">${LONG[k]} <b id="wv_${k}">${state.weights[k]}</b></label>` +
        `<input type="range" id="w_${k}" min="0" max="50" step="5" value="${state.weights[k]}" aria-describedby="weightText"></div>`).join("");
      KEYS.forEach((k) => {
        const inp = $("w_" + k);
        inp.oninput = () => { $("wv_" + k).textContent = inp.value; };
        inp.onchange = () => { state.weights[k] = Number(inp.value); refresh(); };
      });
      $("weightReset").onclick = () => { state.weights = Object.assign({}, P.defaultWeights); refresh(); };
      const p = state.profile;
      $("weightText").textContent = "현재 비중: " + weightText(state.weights) + (p ? ` (금융 MBTI ${p.type} → ${p.weightLabel} 기본값에서 시작)` : "");
      const r = IND[state.industry];
      $("corrTable").innerHTML = corrTable();
      if (!r.scored) {
        $("scoreStatus").innerHTML = `<b>${esc(r.name)}</b>은(는) 점수를 만들지 않았습니다. 사유: ${esc(r.reason)} (평균 점포 5개 이상 비교 상권 ${nf(r.peers)}곳, 기준 30곳)`;
        $("scoreBody").hidden = true;
        return;
      }
      $("scoreBody").hidden = false;
      const c = scoreRows(), st = r.status;
      $("scoreStatus").innerHTML = `<b>${esc(r.name)}</b>: 점수 대상 ${nf(c.rows.length)}곳 · 종합 점수 있음 ${nf(c.ranked)}곳 · 점수 제외(평균 점포 5개 미만, 참고용) ${nf(st["점포 5개 미만 (참고용)"] || 0)}곳` +
        (r.salesScored ? "" : ` · <b>매출 영역 없음</b> (${r.salesSupplied ? "매출 비교 상권 부족" : "매출 미제공 업종"})`);
      if (state.selected === null || !c.by.has(state.selected)) state.selected = c.rows.length ? c.rows[0].i : null;
      drawScoreMap(c);
      drawRankTable(c);
      drawDetail(c);
    }
    function drawScoreMap(c) {
      const s = seq(), stores = storeMap(state.industry), miss = tok("missing"), out = tok("out");
      const matched = state.profile ? state.profile.matched : null;
      drawMap($("scoreMap"), {
        label: `${IND[state.industry].name} 종합 점수 지도`,
        fill: (i) => { const r = c.by.get(i); if (r) return r.total === null ? miss : s[bin5(r.total)]; return stores.has(i) ? miss : out; },
        outline: state.selected !== null ? [state.selected] : [],
        tip: (i) => {
          const r = c.by.get(i), head = `${A.name[i]}\n${A.gu[i]} · ${A.kind[i]} · 금융 MBTI ${typeText(i)}` + (matched ? ` (${C.matchLabel(A.type2[i], matched)})` : "");
          if (r) return `${head}\n종합 점수 ${s1f(r.total)}${r.rank ? ` (${r.rank}위 / ${c.ranked}곳)` : ""} · ${r.used}개 영역\n평균 점포 ${nf(r.stores, 1)}개`;
          return stores.has(i) ? `${head}\n점수 없음: 평균 점포 ${nf(stores.get(i), 1)}개 (5개 미만, 참고용)` : `${head}\n이 업종 점포 없음`;
        },
        click: (i) => { if (c.by.has(i)) { state.selected = i; drawScoreMap(c); drawRankTable(c); drawDetail(c); } },
      });
      $("scoreLegend").innerHTML = rampLegend(["0 낮음", "100 높음", "0~20", "20~40", "40~60", "60~80", "80~100"], [[miss, "점수 없음 (점포 5개 미만)"], [out, "이 업종 점포 없음"]]);
    }
    function drawRankTable(c) {
      const p = state.profile;
      $("onlyMatchWrap").hidden = !p;
      const om = $("onlyMatch");
      om.checked = state.onlyMatch;
      om.onchange = () => { state.onlyMatch = om.checked; state.rankLimit = 15; drawRankTable(c); };
      const q = $("rankQuery");
      q.value = state.rankQuery;
      q.oninput = () => { state.rankQuery = q.value; state.rankLimit = 15; drawRankTable(c); };
      const query = state.rankQuery.trim();
      let rows = c.rows;
      if (p && state.onlyMatch) rows = rows.filter((r) => C.matchLabel(A.type2[r.i], p.matched) !== C.OTHER && A.type2[r.i]);
      if (query) rows = rows.filter((r) => (A.name[r.i] + " " + A.gu[r.i]).indexOf(query) >= 0);
      const cols = [
        { k: "rank", l: "전체 순위", num: true, f: (v) => (v ? v : "—") }, { k: (r) => A.name[r.i], l: "상권", cls: "name" }, { k: (r) => A.gu[r.i], l: "자치구", cls: "nowrap" },
        { k: "total", l: "종합", num: true, f: s1f }, { k: "sales", l: "매출", num: true, f: s1f }, { k: "competition", l: "경쟁", num: true, f: s1f },
        { k: "stability", l: "안정성", num: true, f: s1f }, { k: "demand", l: "수요", num: true, f: s1f }, { k: "stores", l: "점포", num: true, f: (v) => nf(v, 1) },
      ];
      if (p) cols.splice(4, 0, { k: (r) => A.type2[r.i], l: "MBTI", html: (v) => matchBadge(v, p.matched) });
      $("rankTable").innerHTML = table(cols, rows.slice(0, state.rankLimit), {
        rowAttr: (r) => ` class="click${r.i === state.selected ? " sel" : ""}" data-i="${r.i}" tabindex="0" aria-selected="${r.i === state.selected}"`,
      });
      const pick = (e) => { const tr = e.target.closest("tr[data-i]"); if (tr) { state.selected = Number(tr.getAttribute("data-i")); drawScoreMap(c); drawRankTable(c); drawDetail(c); } };
      $("rankTable").onclick = pick;
      $("rankTable").onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(e); } };
      const more = $("rankMore");
      more.hidden = rows.length <= state.rankLimit;
      more.textContent = `더 보기 (${nf(Math.min(rows.length, state.rankLimit))} / ${nf(rows.length)}곳)`;
      more.onclick = () => { state.rankLimit += 15; drawRankTable(c); };
    }
    function matchBadge(type2, matched) {
      const m = C.matchLabel(type2, matched), cls = m === C.MATCH ? "match" : m === C.NEAR ? "near" : "";
      const short = m === C.MATCH ? "일치" : m === C.NEAR ? "경계" : m === C.OTHER ? "다름" : "";
      return `<span class="badge ${cls}" title="${esc(m)}">${esc(type2 || "판정 불가")}${short ? " " + short : ""}</span>`;
    }
    function drawDetail(c) {
      const host = $("detail"), r = c.by.get(state.selected);
      if (!r) { host.innerHTML = '<p class="empty">지도나 표에서 상권을 고르세요.</p>'; return; }
      const i = r.i, m = c.med;
      const bars = KEYS.map((k) => `<div class="bar-row" data-tip="${esc(`${LONG[k]} ${s1f(r[k])}점 · 서울 같은 업종 중앙값 ${s1f(m[k])}점`)}"><span>${LONG[k]}</span>` +
        `<div class="bar-track">${isNum(r[k]) ? `<div class="bar-fill" style="width:${r[k]}%"></div>` : ""}${isNum(m[k]) ? `<div class="bar-med" style="left:calc(${m[k]}% - 1px)"></div>` : ""}</div>` +
        `<span class="num">${isNum(r[k]) ? s1f(r[k]) : "자료 없음"}</span></div>`).join("");
      const raw = [
        ["점포당 월매출", man(r.salesMonth), man(m.salesMonth), r.salesNote || ""],
        ["경쟁: 유동 1,000명당 같은 업종 점포", nf(r.comp, 4), nf(m.comp, 4), "낮을수록 경쟁 점수가 높음"],
        ["축소 추정 폐업률", pct(r.close, 2), pct(m.close, 2), "낮을수록 안정성 점수가 높음 (1년치)"],
        ["유동인구 밀도 백분위", s1f(r.pf), s1f(m.pf), "수요 구성 1"], ["직장인구 밀도 백분위", s1f(r.pw), s1f(m.pw), "수요 구성 2 (2024Q4 값)"],
        ["상주인구 밀도 백분위", s1f(r.pr), s1f(m.pr), "수요 구성 3 (2023Q4 값)"],
        ["평균 점포 수 · 연간 개업 / 폐업", `${nf(r.stores, 1)}개 · ${nf(r.opens)} / ${nf(r.closes)}`, `${nf(m.stores, 1)}개`, "2025년 4개 분기"],
      ];
      host.innerHTML = `<div class="detail-head"><h3>${esc(A.name[i])} <span class="note">${esc(A.gu[i])} · ${esc(A.kind[i])} · 금융 MBTI 상권 유형 ${esc(typeText(i))}</span></h3>` +
        `<span>종합 <b>${s1f(r.total)}</b>점${r.rank ? ` · ${r.rank}위 / ${nf(c.ranked)}곳` : ""} · ${r.used}개 영역 <button type="button" class="ghost" id="toRadar">시각화 6 비교에 담기</button></span></div>` +
        `<div class="grid2"><div><div class="bars">${bars}</div><p class="note">막대 = 이 상권, 세로선 = 서울 같은 업종 점수 대상의 중앙값. 점수는 같은 업종 안 백분위입니다.</p></div>` +
        `<div class="table-wrap">${table([{ k: 0, l: "원값" }, { k: 1, l: "이 상권", num: true }, { k: 2, l: "업종 중앙값", num: true }, { k: 3, l: "메모" }], raw)}</div></div>`;
      $("toRadar").onclick = () => {
        const cur = compareList(scoreRows());
        if (cur.indexOf(i) < 0) { cur.unshift(i); state.compare = cur.slice(0, 3); }
        location.hash = "#v6";
      };
    }
    function corrTable() {
      const m = P.step4.correlation, ks = ["score_sales", "score_competition", "score_stability", "score_demand"], nm = { score_sales: "매출", score_competition: "경쟁", score_stability: "안정성", score_demand: "수요" };
      return table([{ k: "n", l: "" }].concat(ks.map((k) => ({ k: k, l: nm[k], num: true, f: (v) => v.toFixed(2) }))), ks.map((a) => Object.assign({ n: nm[a] }, Object.fromEntries(ks.map((b) => [b, m[a][b]])))));
    }

    // ------------------------------------------------------------ 7. 금융 MBTI
    function renderS7() {
      const seg = $("mbtiMode");
      seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-selected", String(b.getAttribute("data-mode") === state.mode)));
      seg.onclick = (e) => { const b = e.target.closest("[data-mode]"); if (b) { state.mode = b.getAttribute("data-mode"); renderS7(); } };
      drawMbtiInput();
      drawMbtiResult();
      drawReco();
      $("step5Design").innerHTML = autoTable(P.step5.design);
      $("typeTable").innerHTML = autoTable(P.step5.types);
      $("sgTable").innerHTML = autoTable(P.step5.weights);
    }
    function drawMbtiInput() {
      const host = $("mbtiInput");
      if (state.mode === "survey") {
        const r = surveyResult();
        host.innerHTML = `<div class="table-head"><h3>15문항 검사</h3><button type="button" class="ghost" id="clearAnswers">응답 지우기</button></div>` +
          `<p class="note">둘 중 더 가까운 쪽을 고르세요. 문항 순서는 섞었고 어느 글자인지는 숨겼습니다. ${r.answered}/15 답함</p>` +
          `<div class="progress" aria-hidden="true"><i style="width:${(r.answered / 15) * 100}%"></i></div>` +
          QUESTIONS.map((q, k) => {
            const no = q["번호"], a = state.answers[no];
            return `<div class="q" role="group" aria-label="문항 ${k + 1}"><p>${k + 1}. ${esc(q["질문"])}</p><div class="opts">` +
              ["A", "B"].map((x) => `<button type="button" data-q="${no}" data-a="${x}" aria-pressed="${a === x}">${esc(q[x])}</button>`).join("") + "</div></div>";
          }).join("");
        host.onclick = (e) => {
          if (e.target.closest("#clearAnswers")) { state.answers = {}; renderS7(); return; }
          const b = e.target.closest("[data-q]");
          if (!b) return;
          state.answers[b.getAttribute("data-q")] = b.getAttribute("data-a");
          b.parentNode.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
          const rr = surveyResult();
          host.querySelector(".progress i").style.width = (rr.answered / 15) * 100 + "%";
          host.querySelector(".note").textContent = `둘 중 더 가까운 쪽을 고르세요. 문항 순서는 섞었고 어느 글자인지는 숨겼습니다. ${rr.answered}/15 답함`;
          drawMbtiResult();
          drawReco();
        };
      } else {
        host.innerHTML = `<h3>유형 직접 고르기</h3><p class="note">검사를 하지 않고 유형을 고릅니다. 이때는 경계 유형 없이 세 글자를 모두 뚜렷한 것으로 봅니다.</p><div class="types">` +
          TYPE_ORDER.map((t) => `<button type="button" data-t="${t}" aria-pressed="${state.pick === t}">${TYPES[t]["이모지"]} <b>${t}</b> ${esc(TYPES[t]["이름"])}<small>${esc(TYPES[t]["상권 특징"])}</small></button>`).join("") + "</div>";
        host.onclick = (e) => { const b = e.target.closest("[data-t]"); if (b) { state.pick = b.getAttribute("data-t"); renderS7(); } };
      }
    }
    function drawMbtiResult() {
      const host = $("mbtiResult"), p = pendingProfile(), applied = state.profile;
      if (!p) {
        const r = surveyResult();
        host.innerHTML = `<h3>결과</h3>` + (state.mode === "survey"
          ? `<p class="note">기준마다 5문항을 모두 답하면 글자가 정해집니다.</p><dl class="kv">${r.axes.map((a) => `<dt>${esc(a.axis)}</dt><dd>${a.letter ? `${a.letter} (${a.counts[a.left]}:${a.counts[a.right]})` : `${a.answered}/${a.total}문항`}</dd>`).join("")}</dl>`
          : `<p class="note">왼쪽에서 유형을 고르세요.</p>`) +
          (applied ? `<p class="note">지금 적용 중: <b>${applied.type}</b> ${esc(applied.info["이름"])}</p><div class="actions"><button type="button" class="ghost" data-act="off">적용 해제</button></div>` : "");
      } else {
        const same = applied && applied.type === p.type && applied.text === p.text;
        host.innerHTML = `<div class="result-type">${p.info["이모지"]} ${p.type}</div><div class="result-name">${esc(p.info["이름"])}</div>` +
          `<dl class="kv"><dt>판정</dt><dd>${esc(p.text)}</dd><dt>상권 특징</dt><dd>${esc(p.info["상권 특징"])}</dd>` +
          `<dt>창업 아이템 예시</dt><dd>${esc(p.info["창업 아이템 예시"])} <span class="note">(팀 유형표의 예시)</span></dd>` +
          `<dt>맞춰 볼 상권</dt><dd>${Object.entries(p.matched).map(([k, v]) => `${k}(${v})`).join(" · ")}</dd>` +
          `<dt>가중치</dt><dd>${esc(p.weightLabel)}: ${KEYS.map((k) => `${SHORT[k]} ${p.weights[k]}`).join(" · ")}</dd></dl>` +
          `<p class="note">S/G는 상권에서 판정하지 않고 점수 가중치로만 씁니다.</p><div class="actions">` +
          (same ? `<span class="status done">● 적용 중</span><button type="button" class="ghost" data-act="off">적용 해제</button>`
            : `<button type="button" class="primary" data-act="on">이 유형 적용하기</button>${applied ? '<button type="button" class="ghost" data-act="off">적용 해제</button>' : ""}`) + "</div>";
      }
      host.onclick = (e) => {
        const b = e.target.closest("[data-act]");
        if (!b) return;
        applyProfile(b.getAttribute("data-act") === "on" ? pendingProfile() : null);
      };
    }
    function activeProfile() {
      if (state.profile) return { p: state.profile, weights: state.weights, applied: true };
      const p = pendingProfile();
      return p ? { p: p, weights: p.weights, applied: false } : null;
    }
    function drawReco() {
      const ap = activeProfile(), r = IND[state.industry];
      $("recoTitle").textContent = `${r.name}: 유형이 맞는 상권`;
      const body = $("recoBody");
      if (!ap) {
        $("recoNote").textContent = "검사를 끝내거나 유형을 고르면 희망 업종에서 유형이 맞는 상권이 여기에 나옵니다.";
        body.hidden = true;
        drawQuadrant(null);
        return;
      }
      if (!r.scored) {
        $("recoNote").textContent = `${r.name}은(는) 점수를 만들지 않아 추천 목록이 없습니다. 사유: ${r.reason}`;
        body.hidden = true;
        drawQuadrant(ap.p.matched);
        return;
      }
      body.hidden = false;
      const c = scoreRows(ap.weights), matched = ap.p.matched;
      const hit = c.rows.filter((x) => A.type2[x.i] && matched[A.type2[x.i]]);
      const nm = hit.filter((x) => matched[A.type2[x.i]] === C.MATCH).length;
      $("recoNote").textContent = `${ap.applied ? "적용 중인" : "아직 적용하지 않은"} ${ap.p.type} 기준 · 가중치 ${weightText(ap.weights)} · 점수 대상 ${nf(c.rows.length)}곳 중 일치 ${nf(nm)}곳` +
        (hit.length > nm ? `, 경계 유형 ${nf(hit.length - nm)}곳` : "") + ". 순서는 성공 가능성이 아니라 업종 내 비교 점수입니다.";
      const out = tok("out"), neutral = tok("neutral"), s1c = tok("s1"), s2c = tok("s2");
      drawMap($("mbtiMap"), {
        label: "금융 MBTI 유형이 맞는 상권 지도",
        fill: (i) => { const x = c.by.get(i); if (!x) return out; const m = C.matchLabel(A.type2[i], matched); return m === C.MATCH ? s1c : m === C.NEAR ? s2c : neutral; },
        tip: (i) => { const x = c.by.get(i); return `${A.name[i]} (${A.gu[i]})\n상권 유형 ${typeText(i)} · ${C.matchLabel(A.type2[i], matched)}` + (x ? `\n종합 점수 ${s1f(x.total)}` : "\n이 업종 점수 대상 아님"); },
      });
      $("mbtiMapNote").textContent = "점수 대상 상권만 색칠합니다";
      $("mbtiLegend").innerHTML = [[s1c, "일치"], [s2c, "경계 유형 (3:2)"], [neutral, "다른 유형 · 판정 불가"], [out, "점수 대상 아님"]]
        .filter((x) => x[1] !== "경계 유형 (3:2)" || Object.values(matched).indexOf(C.NEAR) >= 0)
        .map(([col, t]) => `<span><span class="sw" style="background:${col}"></span>${t}</span>`).join("");
      $("recoTable").innerHTML = table([
        { k: (x, k) => k + 1, l: "#", num: true }, { k: (x) => A.name[x.i], l: "상권", cls: "name" }, { k: (x) => A.gu[x.i], l: "자치구", cls: "nowrap" },
        { k: (x) => A.type2[x.i], l: "상권 유형", html: (v) => matchBadge(v, matched) }, { k: "total", l: "종합", num: true, f: s1f },
        { k: "sales", l: "매출", num: true, f: s1f }, { k: "competition", l: "경쟁", num: true, f: s1f }, { k: "stability", l: "안정성", num: true, f: s1f }, { k: "demand", l: "수요", num: true, f: s1f },
      ], hit.slice(0, 20)) + `<p class="note">상위 20곳. 전체 목록은 6장 표에서 "금융 MBTI 유형이 맞는 상권만"을 켜면 볼 수 있습니다(적용 후).</p>`;
      drawQuadrant(matched);
    }
    function drawQuadrant(matched) {
      const W = 620, Hh = 440, m = { l: 52, r: 16, t: 14, b: 44 }, x = lin(0, 100, m.l, W - m.r), y = lin(0, 100, Hh - m.b, m.t);
      const med = P.step5.medians, s1c = tok("s1"), s2c = tok("s2"), gray = tok("missing"), surf = tok("surface");
      const pts = [];
      for (let i = 0; i < NA; i++) {
        if (!isNum(A.lvs[i]) || !isNum(A.eps[i])) continue;
        const lab = matched ? C.matchLabel(A.type2[i], matched) : null;
        pts.push({ i: i, x: x(A.lvs[i]), y: y(A.eps[i]), c: lab === C.MATCH ? s1c : lab === C.NEAR ? s2c : gray, front: lab === C.MATCH || lab === C.NEAR });
      }
      pts.sort((a, b) => a.front - b.front);
      let s = `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="상권 L/V 점수와 E/P 점수 산점도">`;
      [0, 25, 50, 75, 100].forEach((v) => {
        s += `<line class="gl" x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/><text class="tick" x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
        s += `<text class="tick" x="${x(v)}" y="${Hh - m.b + 16}" text-anchor="middle">${v}</text>`;
      });
      s += `<line x1="${x(med.lv_score)}" x2="${x(med.lv_score)}" y1="${m.t}" y2="${Hh - m.b}" stroke="${tok("ink2")}" stroke-width="1"/>`;
      s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(med.ep_score)}" y2="${y(med.ep_score)}" stroke="${tok("ink2")}" stroke-width="1"/>`;
      pts.forEach((p) => { s += `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${p.front ? 3.6 : 2.6}" fill="${p.c}" fill-opacity="${p.front ? 0.9 : matched ? 0.45 : 0.6}" stroke="${surf}" stroke-width="${p.front ? 1 : 0}"/>`; });
      // 사분면 이름: 오른쪽이 V(L/V 점수가 높음), 위쪽이 P(E/P 점수가 높음)
      [["L · P", m.l + 8, m.t + 16, "start"], ["V · P", W - m.r - 8, m.t + 16, "end"], ["L · E", m.l + 8, Hh - m.b - 10, "start"], ["V · E", W - m.r - 8, Hh - m.b - 10, "end"]]
        .forEach(([t, tx, ty, an]) => { s += `<text x="${tx}" y="${ty}" text-anchor="${an}" style="font-size:13px;font-weight:650;fill:${tok("ink")};paint-order:stroke;stroke:${surf};stroke-width:3px">${t}</text>`; });
      s += `<text x="${(m.l + W - m.r) / 2}" y="${Hh - 6}" text-anchor="middle">L/V 점수 → 높을수록 V(방문형)</text>`;
      s += `<text transform="translate(14 ${(m.t + Hh - m.b) / 2}) rotate(-90)" text-anchor="middle">E/P 점수 → 높을수록 P(프리미엄형)</text>`;
      s += `<circle id="qHi" r="6" fill="none" stroke="${tok("ink")}" stroke-width="2" visibility="hidden"/>`;
      s += `<rect data-owntip x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${Hh - m.t - m.b}" fill="transparent"/></svg>`;
      const host = $("quadrant");
      host.innerHTML = s;
      nearestHover(host, pts, (p) => `${A.name[p.i]} (${A.gu[p.i]})\n상권 유형 ${typeText(p.i)}${matched ? " · " + C.matchLabel(A.type2[p.i], matched) : ""}\nL/V ${s1f(A.lvs[p.i])} · E/P ${s1f(A.eps[p.i])}`, "qHi");
      $("quadLegend").innerHTML = matched
        ? [[s1c, "일치"], [s2c, "경계 유형"], [gray, "다른 유형"]].map(([c2, t]) => `<span><span class="sw" style="background:${c2}"></span>${t}</span>`).join("") + `<span>판정 상권 ${nf(pts.length)}곳</span>`
        : `<span><span class="sw" style="background:${gray}"></span>상권 ${nf(pts.length)}곳 (유형을 정하면 맞는 상권이 색으로 표시됩니다)</span>`;
    }
    function nearestHover(host, pts, text, hiId) {
      const svg = host.querySelector("svg"), rect = host.querySelector("rect[data-owntip]"), hi = svg.querySelector("#" + hiId);
      rect.onpointermove = (e) => {
        const ctm = svg.getScreenCTM();
        if (!ctm) return;
        const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
        let best = null, bd = 24 * 24;
        pts.forEach((p) => { const d = (p.x - pt.x) * (p.x - pt.x) + (p.y - pt.y) * (p.y - pt.y); if (d < bd) { bd = d; best = p; } });
        if (best) { hi.setAttribute("cx", best.x); hi.setAttribute("cy", best.y); hi.setAttribute("visibility", "visible"); showTip(text(best), e.clientX, e.clientY); }
        else { hi.setAttribute("visibility", "hidden"); hideTip(); }
      };
      rect.onpointerleave = () => { hi.setAttribute("visibility", "hidden"); hideTip(); };
    }

    // ------------------------------------------------------------ 8. STEP 6 시각화 7종
    const VIZ = [
      { id: "v1", draw: drawV1 }, { id: "v2", draw: drawV2 }, { id: "v3", draw: drawV3 }, { id: "v4", draw: drawV4 },
      { id: "v5", draw: drawV5 }, { id: "v6", draw: drawV6 }, { id: "v7", draw: drawV7 },
    ];
    function renderS8() {
      const D = P.step6.design;
      $("step6Design").innerHTML = autoTable(D);
      $("vizPills").innerHTML = D.map((d) => `<a href="#v${d["번호"]}">${d["번호"]}. ${esc(d["시각화"])}</a>`).join("");
      const host = $("vizCards");
      if (!host.childElementCount) {
        host.innerHTML = D.map((d) => `<article class="card viz" id="v${d["번호"]}" aria-labelledby="vt${d["번호"]}">` +
          `<div class="viz-head"><span class="no">${d["번호"]}</span><h3 id="vt${d["번호"]}">${esc(d["시각화"])}</h3><span class="tag">${esc(d["상태"])}</span></div>` +
          `<div class="viz-meta"><div><b>분석 목적</b>${esc(d["분석 목적"])}</div><div><b>필요한 데이터</b>${esc(d["필요한 데이터"])}</div>` +
          `<div><b>구현 방법</b>${esc(d["구현 방법"])}</div><div><b>기대 인사이트</b>${esc(d["기대 인사이트"])}</div></div>` +
          `<div class="viz-controls" id="v${d["번호"]}c"></div><div class="chart-box" id="v${d["번호"]}g"></div><div class="legend" id="v${d["번호"]}l"></div>` +
          `<p class="found" id="v${d["번호"]}f"></p><details class="fold"><summary>표로 보기</summary><div class="table-wrap" id="v${d["번호"]}t"></div></details></article>`).join("");
      }
      VIZ.forEach((v) => v.draw());
    }
    function segButtons(host, items, cur, onPick) {
      host.innerHTML = `<div class="seg">${items.map(([v, t]) => `<button type="button" aria-pressed="${v === cur}" data-v="${v}">${esc(t)}</button>`).join("")}</div>`;
      host.onclick = (e) => { const b = e.target.closest("[data-v]"); if (b) onPick(b.getAttribute("data-v")); };
    }
    const found = (id, html) => { $(id + "f").innerHTML = "<b>확인한 결과</b> · " + html; };

    function drawV1() {
      const r = IND[state.industry], stores = storeMap(state.industry), out = tok("out");
      segButtons($("v1c"), [["industry", `선택 업종 점포 수 (${r.name})`], ["group", "상권별 최다 업종군"]], state.v1, (v) => { state.v1 = v; drawV1(); });
      const g = $("v1g");
      g.classList.add("map");
      g.style.maxWidth = "760px";
      if (state.v1 === "industry") {
        const s = seq(), cuts = [2, 5, 10, 20], cls = (v) => cuts.filter((c) => v >= c).length;
        drawMap(g, {
          label: `${r.name} 상권별 평균 점포 수 지도`,
          fill: (i) => (stores.has(i) ? s[cls(stores.get(i))] : out),
          tip: (i) => `${areaLabel(i)} · ${A.kind[i]}\n${r.name} 평균 점포 ${stores.has(i) ? nf(stores.get(i), 2) : 0}개 (2025년 4개 분기 평균)`,
        });
        $("v1l").innerHTML = rampLegend(["적음", "많음", "2개 미만", "2~5개", "5~10개", "10~20개", "20개 이상"], [[out, "점포 없음"]]);
        const list = [...stores.entries()].sort((a, b) => b[1] - a[1]), k = Math.max(1, Math.ceil(list.length * 0.1));
        const total = list.reduce((s2, x) => s2 + x[1], 0), top = list.slice(0, k).reduce((s2, x) => s2 + x[1], 0);
        found("v1", `${esc(r.name)}: 점포가 있는 상권 ${nf(list.length)}곳 중 상위 10%(${nf(k)}곳)에 점포의 <b>${(total ? (top / total) * 100 : 0).toFixed(1)}%</b>가 있습니다. 업종마다 몰린 곳이 달라 점수는 업종 안에서 비교합니다.`);
        $("v1t").innerHTML = table([{ k: (x, j) => j + 1, l: "#", num: true }, { k: (x) => areaLabel(x[0]), l: "상권" }, { k: (x) => A.kind[x[0]], l: "상권 유형" }, { k: (x) => x[1], l: "평균 점포", num: true, f: (v) => nf(v, 2) }], list.slice(0, 30)) + '<p class="note">점포가 많은 30곳</p>';
      } else {
        const col = cat(), dom = (i) => { const v = A.grp[i], mx = Math.max(v[0], v[1], v[2]); return mx > 0 ? v.indexOf(mx) : -1; };
        const counts = [0, 0, 0];
        for (let i = 0; i < NA; i++) { const d = dom(i); if (d >= 0) counts[d] += 1; }
        drawMap(g, {
          label: "상권별 점포가 가장 많은 업종군 지도",
          fill: (i) => { const d = dom(i); return d >= 0 ? col[d] : out; },
          tip: (i) => { const v = A.grp[i], t = v[0] + v[1] + v[2]; return `${areaLabel(i)} · ${A.kind[i]}\n` + GROUPS.map((gname, k) => `${gname} ${nf(v[k], 1)}개 (${t ? ((v[k] / t) * 100).toFixed(0) : 0}%)`).join("\n"); },
        });
        $("v1l").innerHTML = GROUPS.map((gname, k) => `<span><span class="sw" style="background:${col[k]}"></span>${gname} ${nf(counts[k])}곳</span>`).join("");
        found("v1", `상권 ${nf(NA)}곳 중 점포가 가장 많은 업종군은 외식 ${nf(counts[0])}곳 · 서비스 ${nf(counts[1])}곳 · 소매 ${nf(counts[2])}곳입니다. 서울 서비스 업종 100개는 외식 10 · 서비스 47 · 소매 43개로 나뉩니다.`);
        $("v1t").innerHTML = table([{ k: (x) => x[0], l: "업종군" }, { k: (x) => x[1], l: "최다 업종군인 상권", num: true, f: nf }], GROUPS.map((gname, k) => [gname, counts[k]]));
      }
    }

    function drawV2() {
      const H = P.viz.heat, M = state.v2 === "area" ? H.area : H.gu;
      segButtons($("v2c"), [["area", "매출 상위 20개 상권"], ["gu", "25개 자치구"]], state.v2, (v) => { state.v2 = v; drawV2(); });
      const s = seq(), cuts = [5, 10, 20, 40], cls = (v) => cuts.filter((c) => v >= c).length;
      const cw = 58, ch = 24, lw = 210, top = 92, rw = 250, nx = lw + cw * H.industries.length + 14, W = lw + cw * H.industries.length + rw + 10, Hh = top + ch * M.rows.length + 8;
      let svg = `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="${esc(M.label)}별 업종 매출 비중 히트맵" style="min-width:860px">`;
      svg += `<text x="${nx}" y="${top - 10}" class="lbl" style="font-weight:600">1위 업종 (비중)</text>`;
      H.industries.forEach((name, j) => {
        const cx = lw + j * cw + cw / 2;
        svg += `<text transform="translate(${cx + 4} ${top - 8}) rotate(-40)" class="lbl" style="font-size:11.5px">${esc(name)}</text>`;
      });
      svg += `<text x="${W - 10}" y="${top - 10}" text-anchor="end" class="lbl" style="font-weight:600">총매출(억원)</text>`;
      M.rows.forEach((row, k) => {
        const y = top + k * ch;
        svg += `<text x="${lw - 8}" y="${y + ch / 2 + 4}" text-anchor="end" class="lbl">${esc(row.length > 22 ? row.slice(0, 21) + "…" : row)}</text>`;
        M.share[k].forEach((v, j) => {
          const x = lw + j * cw, c = cls(v);
          svg += `<rect x="${x + 1}" y="${y + 1}" width="${cw - 2}" height="${ch - 2}" rx="3" fill="${v > 0 ? s[c] : tok("surface-2")}" data-tip="${esc(`${row}\n${H.industries[j]}: 매출의 ${v.toFixed(1)}% (${nf((M.total[k] * v) / 100, 0)}억원)`)}"/>`;
          if (v >= 20) svg += `<text x="${x + cw / 2}" y="${y + ch / 2 + 4}" text-anchor="middle" style="font-size:11px;fill:${onFill(s[c])};pointer-events:none">${v.toFixed(0)}</text>`;
        });
        const over = M.leadShare[k] > 50;
        svg += `<text x="${nx}" y="${y + ch / 2 + 4}" class="lbl" style="font-size:11.5px;${over ? "font-weight:700" : ""}">${esc(M.lead[k])} ${M.leadShare[k].toFixed(0)}%</text>`;
        svg += `<text x="${W - 10}" y="${y + ch / 2 + 4}" text-anchor="end" class="tick" style="font-size:11px">${nf(M.total[k])}</text>`;
      });
      const g = $("v2g");
      g.className = "chart-box table-wrap";
      g.innerHTML = svg + "</svg>";
      $("v2l").innerHTML = rampLegend(["행 매출 중 비중", "", "5% 미만", "5~10%", "10~20%", "20~40%", "40% 이상"], [[tok("surface-2"), "매출 없음"]]) + '<span>칸 안 숫자는 20% 이상만 표시</span>';
      const over = M.leadShare.filter((v) => v > 50).length;
      found("v2", state.v2 === "area"
        ? `매출 상위 20개 상권 중 <b>${over}곳</b>은 1위 업종이 매출의 50%를 넘습니다. 상권 총매출 순위는 입지보다 특정 업종의 쏠림을 반영합니다. 서울 합계 ${H.seoulTotal}조원(관광특구 제외, 4개 분기 관측 합).`
        : `25개 자치구 중 1위 업종 비중이 50%를 넘는 곳은 ${over}곳입니다. 자치구 단위로 묶으면 업종 구성이 고르게 보여, 쏠림은 상권 단위에서 두드러집니다.`);
      $("v2t").innerHTML = table([{ k: (x) => x.row, l: M.label }, { k: (x) => x.total, l: "총매출(억원)", num: true, f: nf }, { k: (x) => x.lead, l: "1위 업종" }, { k: (x) => x.ls, l: "1위 업종 비중", num: true, f: (v) => v.toFixed(1) + "%" }]
        .concat(H.industries.map((n, j) => ({ k: (x) => x.share[j], l: n, num: true, f: (v) => v.toFixed(1) }))), M.rows.map((row, k) => ({ row: row, total: M.total[k], lead: M.lead[k], ls: M.leadShare[k], share: M.share[k] })));
    }

    function drawV3() {
      const all = P.viz.density, cur = state.industry;
      const top = all.slice().sort((a, b) => b.stores - a.stores).slice(0, 25);
      if (!top.some((d) => d.code === cur)) top.push(all.find((d) => d.code === cur));
      top.sort((a, b) => b.p50 - a.p50);
      const W = 900, lw = 170, rh = 22, t = 24, Hh = t + rh * top.length + 34, lo = 0.5, hi = 2000, x = logs(lo, hi, lw, W - 20);
      const c1 = tok("s1"), c2 = tok("s2"), band = tok("seq2"), surf = tok("surface");
      let s = `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="업종별 면적당 점포 수 범위">`;
      logTicks(lo, hi).filter((v) => [1, 10, 100, 1000].indexOf(v) >= 0 || v === 0.5 || v === 2000).forEach((v) => {
        s += `<line class="gl" x1="${x(v)}" x2="${x(v)}" y1="${t - 6}" y2="${Hh - 30}"/><text class="tick" x="${x(v)}" y="${Hh - 14}" text-anchor="middle">${nf(v, v < 1 ? 1 : 0)}</text>`;
      });
      s += `<text x="${(lw + W) / 2}" y="${Hh - 1}" text-anchor="middle">면적당 점포 수 (개/㎢, 로그 축) · 점포가 있는 상권만</text>`;
      top.forEach((d, k) => {
        const y = t + k * rh + rh / 2, sel = d.code === cur, col = sel ? c2 : c1;
        const tipText = `${d.name} (${d.group})\n25 · 50 · 75 백분위: ${nf(d.p25, 1)} · ${nf(d.p50, 1)} · ${nf(d.p75, 1)}개/㎢\n점포가 있는 상권 ${nf(d.n)}곳 · 점포 ${nf(d.stores)}개`;
        s += `<g data-tip="${esc(tipText)}" tabindex="0"><rect x="0" y="${y - rh / 2}" width="${W}" height="${rh}" fill="transparent"/>`;
        s += `<text x="${lw - 10}" y="${y + 4}" text-anchor="end" class="lbl" style="${sel ? "font-weight:700" : ""}">${esc(d.name)}</text>`;
        s += `<line x1="${x(Math.max(d.p25, lo))}" x2="${x(Math.min(d.p75, hi))}" y1="${y}" y2="${y}" stroke="${sel ? c2 : band}" stroke-width="6" stroke-linecap="round" stroke-opacity="${sel ? 0.55 : 1}"/>`;
        s += `<circle cx="${x(Math.min(Math.max(d.p50, lo), hi))}" cy="${y}" r="5" fill="${col}" stroke="${surf}" stroke-width="2"/></g>`;
      });
      $("v3g").innerHTML = s + "</svg>";
      $("v3c").innerHTML = '<span class="note">점포 수 상위 25개 업종(선택 업종이 빠지면 함께 표시), 중앙값 순</span>';
      $("v3l").innerHTML = `<span><span class="sw" style="background:${c1};border-radius:50%"></span>중앙값</span><span><span class="sw" style="background:${band};height:6px"></span>25~75 백분위</span><span><span class="sw" style="background:${c2};border-radius:50%"></span>선택 업종</span>`;
      const ranked = all.slice().sort((a, b) => b.p50 - a.p50), me = ranked.findIndex((d) => d.code === cur), d = ranked[me];
      found("v3", `${esc(d.name)}의 면적당 점포 수 중앙값은 <b>${nf(d.p50, 1)}개/㎢</b>로 100개 업종 중 ${me + 1}위입니다. 가장 높은 ${esc(ranked[0].name)}(${nf(ranked[0].p50, 1)})와 가장 낮은 업종의 차이가 커서, 점포 수를 업종 구분 없이 감점하면 안 됩니다.`);
      $("v3t").innerHTML = table([{ k: (x2, j) => j + 1, l: "#", num: true }, { k: "name", l: "업종" }, { k: "group", l: "업종군" }, { k: "n", l: "상권 수", num: true, f: nf },
        { k: "p25", l: "25%", num: true, f: (v) => nf(v, 1) }, { k: "p50", l: "중앙값", num: true, f: (v) => nf(v, 1) }, { k: "p75", l: "75%", num: true, f: (v) => nf(v, 1) }], ranked);
    }

    function drawV4() {
      const r = IND[state.industry], SC = P.viz.salesClose, g = $("v4g");
      $("v4c").innerHTML = '<span class="badge">대체 지표: 2024년 자료가 없어 성장률 대신 매출 수준을 씁니다</span>';
      if (!r.scored || !r.salesScored) {
        g.innerHTML = `<p class="empty">${esc(r.name)}은(는) 매출 점수가 없어 그리지 않습니다 (${esc(r.scored ? (r.salesSupplied ? "매출 비교 상권 30곳 미만" : "매출 미제공 업종") : r.reason)}). 매출 점수가 있는 업종을 고르세요.</p>`;
        $("v4l").innerHTML = "";
        found("v4", `매출 점수가 있는 ${SC.industries}개 업종 중 ${SC.negative}개에서 음(−)의 상관이고, 중앙값은 ρ = ${SC.median.toFixed(2)}입니다.`);
        $("v4t").innerHTML = rhoTable(SC);
        return;
      }
      const rows = scoreRows().rows.filter((x) => isNum(x.sales) && isNum(x.salesMonth) && x.salesMonth > 0 && isNum(x.close));
      const rho = C.spearman(rows.map((x) => x.salesMonth), rows.map((x) => x.close));
      const W = 900, Hh = 380, m = { l: 56, r: 16, t: 12, b: 46 };
      const xs = rows.map((x) => x.salesMonth), ys = rows.map((x) => x.close);
      const x0 = Math.pow(10, Math.floor(Math.log10(Math.min(...xs)) * 2) / 2), x1 = Math.pow(10, Math.ceil(Math.log10(Math.max(...xs)) * 2) / 2);
      const yt = niceTicks(0, Math.max(...ys) * 1.05, 5), y1 = yt[yt.length - 1] < Math.max(...ys) ? Math.max(...ys) * 1.05 : yt[yt.length - 1];
      const x = logs(x0, x1, m.l, W - m.r), y = lin(0, y1, Hh - m.b, m.t), c1 = tok("s1"), surf = tok("surface");
      let s = `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="${esc(r.name)} 점포당 월매출과 축소 추정 폐업률 산점도">`;
      yt.forEach((v) => { s += `<line class="gl" x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/><text class="tick" x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${v}%</text>`; });
      logTicks(x0, x1).forEach((v) => { s += `<line class="gl" x1="${x(v)}" x2="${x(v)}" y1="${m.t}" y2="${Hh - m.b}"/><text class="tick" x="${x(v)}" y="${Hh - m.b + 16}" text-anchor="middle">${wonTick(v)}</text>`; });
      s += `<line class="ax" x1="${m.l}" x2="${W - m.r}" y1="${Hh - m.b}" y2="${Hh - m.b}"/>`;
      const pts = rows.map((q) => ({ i: q.i, x: x(q.salesMonth), y: y(q.close), q: q }));
      pts.forEach((p) => { s += `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3.4" fill="${c1}" fill-opacity="0.55" stroke="${surf}" stroke-width="0.8"/>`; });
      s += `<text x="${(m.l + W) / 2}" y="${Hh - 8}" text-anchor="middle">점포당 월매출 (원, 로그 축)</text>`;
      s += `<text transform="translate(14 ${(m.t + Hh - m.b) / 2}) rotate(-90)" text-anchor="middle">축소 추정 폐업률 (%)</text>`;
      s += `<circle id="v4Hi" r="7" fill="none" stroke="${tok("ink")}" stroke-width="2" visibility="hidden"/>`;
      s += `<rect data-owntip x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${Hh - m.t - m.b}" fill="transparent"/></svg>`;
      g.innerHTML = s + rhoStrip(SC, state.industry);
      nearestHover(g, pts, (p) => `${areaLabel(p.i)}\n점포당 월매출 ${man(p.q.salesMonth)}\n축소 추정 폐업률 ${pct(p.q.close, 2)} · 평균 점포 ${nf(p.q.stores, 1)}개`, "v4Hi");
      $("v4l").innerHTML = `<span><span class="sw" style="background:${c1};border-radius:50%"></span>${esc(r.name)} 매출 점수가 있는 상권 ${nf(rows.length)}곳</span>`;
      const word = rho === null ? "계산할 수 없습니다" : Math.abs(rho) < 0.1 ? "거의 관계가 없습니다" : Math.abs(rho) < 0.3 ? (rho < 0 ? "약한 음(−)의 관계입니다" : "약한 양(+)의 관계입니다") : rho < 0 ? "음(−)의 관계입니다" : "양(+)의 관계입니다";
      found("v4", `${esc(r.name)}: 순위상관 <b>ρ = ${rho === null ? "—" : rho.toFixed(2)}</b>, ${word}. 매출 점수가 있는 ${SC.industries}개 업종 중 ${SC.negative}개가 음(−)이고 중앙값은 ${SC.median.toFixed(2)}입니다. 상권 단위에서 매출 수준과 폐업률은 약하게만 연결됩니다. <b>성장률과의 관계는 2024년 자료가 들어온 뒤 같은 틀로 다시 그립니다.</b>`);
      $("v4t").innerHTML = rhoTable(SC);
    }
    function rhoStrip(SC, cur) {
      const W = 900, Hh = 74, x = lin(-0.5, 0.5, 56, W - 16), c1 = tok("seq2"), c2 = tok("s2"), surf = tok("surface");
      let s = `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="업종별 순위상관 분포" style="margin-top:6px">`;
      [-0.5, -0.25, 0, 0.25, 0.5].forEach((v) => { s += `<line class="${v === 0 ? "ax" : "gl"}" x1="${x(v)}" x2="${x(v)}" y1="14" y2="${Hh - 24}"/><text class="tick" x="${x(v)}" y="${Hh - 10}" text-anchor="middle">${v > 0 ? "+" : ""}${v}</text>`; });
      s += `<text x="56" y="10" style="font-size:11px">업종 ${SC.industries}개의 ρ (점 하나 = 업종 하나, 주황 = 선택 업종)</text>`;
      Object.entries(SC.rho).sort((a, b) => (a[0] === cur) - (b[0] === cur)).forEach(([code, v]) => {
        const sel = code === cur;
        s += `<circle cx="${x(v)}" cy="32" r="${sel ? 6 : 4.5}" fill="${sel ? c2 : c1}" stroke="${surf}" stroke-width="1.5" data-tip="${esc(`${IND[code].name}: ρ = ${v.toFixed(2)}`)}"/>`;
      });
      return s + "</svg>";
    }
    const rhoTable = (SC) => table([{ k: (x) => IND[x[0]].name, l: "업종" }, { k: (x) => x[1], l: "ρ (점포당 월매출 × 축소 추정 폐업률)", num: true, f: (v) => v.toFixed(3) }], Object.entries(SC.rho).sort((a, b) => a[1] - b[1]));

    function drawV5() {
      const F = P.viz.facility, keys = F.keys, col = cat().concat([tok("unknown")]), surf = tok("surface");
      segButtons($("v5c"), [["type", "상권 유형별 구성비"], ["top", "집객시설이 많은 상권 15곳"]], state.v5, (v) => { state.v5 = v; drawV5(); });
      const rows = state.v5 === "type" ? F.byType.map((r) => ({ label: r.label, sub: `${nf(r.areas)}곳 · 상권당 ${nf(r.perArea, 1)}개`, values: r.values, total: r.total }))
        : F.top.map((r) => ({ label: `${r.name} (${r.gu})`, sub: `${nf(r.total)}개`, values: r.values, total: r.total }));
      const share = state.v5 === "type", W = 900, lw = 210, rh = share ? 40 : 26, t = 10, Hh = t + rh * rows.length + 30;
      const maxT = Math.max(...rows.map((r) => r.total)), x = share ? lin(0, 100, lw, W - 70) : lin(0, maxT, lw, W - 70);
      let s = `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="집객시설 구성 누적 막대">`;
      (share ? [0, 25, 50, 75, 100] : niceTicks(0, maxT, 5)).forEach((v) => { s += `<line class="gl" x1="${x(v)}" x2="${x(v)}" y1="${t}" y2="${Hh - 26}"/><text class="tick" x="${x(v)}" y="${Hh - 10}" text-anchor="middle">${share ? v + "%" : nf(v)}</text>`; });
      rows.forEach((r, k) => {
        const y = t + k * rh, bh = share ? 22 : 16, by = y + (rh - bh) / 2 - (share ? 4 : 0);
        s += `<text x="${lw - 10}" y="${by + bh / 2 + 4}" text-anchor="end" class="lbl">${esc(r.label.length > 24 ? r.label.slice(0, 23) + "…" : r.label)}</text>`;
        if (share) s += `<text x="${lw - 10}" y="${by + bh / 2 + 18}" text-anchor="end" class="tick">${esc(r.sub)}</text>`;
        let acc = 0;
        r.values.forEach((v, j) => {
          if (v <= 0) return;
          const a = share ? (acc / r.total) * 100 : acc, b = share ? ((acc + v) / r.total) * 100 : acc + v, x0 = x(a), w = Math.max(0, x(b) - x(a) - 2);
          const txt = `${r.label}\n${keys[j]} ${nf(v)}개 (${((v / r.total) * 100).toFixed(1)}%)` + (F.groups[keys[j]] ? `\n${F.groups[keys[j]].join(", ")}` : "\n세부 항목이 비어 있어 종류를 알 수 없음");
          s += `<rect x="${x0.toFixed(1)}" y="${by}" width="${w.toFixed(1)}" height="${bh}" rx="3" fill="${col[j]}" data-tip="${esc(txt)}"/>`;
          if (share && w > 40) s += `<text x="${(x0 + w / 2).toFixed(1)}" y="${by + bh / 2 + 4}" text-anchor="middle" style="font-size:10.5px;fill:${j === 3 ? "#0b0b0b" : j === 5 ? onFill(col[5]) : "#ffffff"};pointer-events:none">${((v / r.total) * 100).toFixed(0)}%</text>`;
          acc += v;
        });
        if (!share) s += `<text x="${x(acc) + 6}" y="${by + bh / 2 + 4}" class="tick">${nf(r.total)}</text>`;
      });
      $("v5g").innerHTML = s + "</svg>";
      $("v5l").innerHTML = keys.map((k, j) => `<span data-tip="${esc(F.groups[k] ? F.groups[k].join(", ") : "총수 − 세부 항목 합")}"><span class="sw" style="background:${col[j]}"></span>${esc(k)}</span>`).join("");
      found("v5", `서울 집객시설 총수의 <b>${F.unknownShare}%</b>는 세부 항목이 비어 있어 종류를 알 수 없습니다. 세부가 있는 시설 중 교통(버스 정거장 · 지하철역 등)이 ${F.transportShareKnown}%입니다. 발달상권은 상권당 시설이 골목상권의 약 ${(F.byType[2].perArea / F.byType[1].perArea).toFixed(1)}배입니다. 집객시설 자료가 없는 상권 ${F.missingAreas}곳은 뺐습니다. 값은 2021Q1 이후 바뀌지 않았습니다.`);
      $("v5t").innerHTML = table([{ k: "label", l: share ? "구분" : "상권" }, { k: "total", l: "총수", num: true, f: nf }].concat(keys.map((k, j) => ({ k: (r) => r.values[j], l: k, num: true, f: nf }))), rows);
    }

    function compareList(c) {
      const valid = (state.compare || []).filter((i) => c.by.has(i));
      if (state.compare && valid.length) return valid.slice(0, 3);
      return c.rows.filter((r) => r.total !== null).slice(0, 3).map((r) => r.i);
    }
    function drawV6() {
      const r = IND[state.industry], g = $("v6g");
      if (!r.scored) {
        $("v6c").innerHTML = ""; $("v6l").innerHTML = ""; $("v6t").innerHTML = "";
        g.innerHTML = `<p class="empty">${esc(r.name)}은(는) 점수를 만들지 않아 레이더를 그리지 않습니다. 사유: ${esc(r.reason)}</p>`;
        found("v6", "점수가 있는 업종을 고르세요.");
        return;
      }
      const c = scoreRows(), list = compareList(c), cols = cat().slice(0, 3);
      const opts = (sel) => `<option value="">선택 안 함</option>` + c.rows.filter((x) => x.total !== null).slice(0, 300)
        .map((x) => `<option value="${x.i}"${x.i === sel ? " selected" : ""}>${x.rank}. ${esc(A.name[x.i])} (${esc(A.gu[x.i])}) ${s1f(x.total)}</option>`).join("");
      const extra = list.filter((i) => (c.by.get(i).rank || 999) > 300);
      $("v6c").innerHTML = `<div class="pick-row">${[0, 1, 2].map((k) => `<label class="field small"><span class="sw" style="background:${cols[k]};width:10px;height:10px;display:inline-block;border-radius:2px"></span>` +
        `<select data-slot="${k}" aria-label="비교 상권 ${k + 1}">${opts(list[k])}${extra.indexOf(list[k]) >= 0 ? `<option value="${list[k]}" selected>${esc(A.name[list[k]])} (${esc(A.gu[list[k]])})</option>` : ""}</select></label>`).join("")}` +
        `<button type="button" class="ghost" id="v6top">종합 점수 상위 3곳</button></div><p class="note">목록은 현재 가중치 종합 점수 상위 300곳입니다. 6장 상세에서 "시각화 6 비교에 담기"로 다른 상권을 넣을 수 있습니다.</p>`;
      $("v6c").onchange = (e) => {
        const sel = e.target.closest("select[data-slot]");
        if (!sel) return;
        const cur = [0, 1, 2].map((k) => list[k] === undefined ? null : list[k]);
        cur[Number(sel.getAttribute("data-slot"))] = sel.value === "" ? null : Number(sel.value);
        state.compare = cur.filter((v) => v !== null);
        if (!state.compare.length) state.compare = [];
        drawV6();
      };
      $("v6top").onclick = () => { state.compare = null; drawV6(); };
      const med = c.med, W = 520, Hh = 440, cx = W / 2, cy = 216, R = 160, ang = [-90, 0, 90, 180].map((d) => (d * Math.PI) / 180);
      const pt = (k, v) => [cx + Math.cos(ang[k]) * R * (v / 100), cy + Math.sin(ang[k]) * R * (v / 100)];
      const ink2 = tok("ink2"), surf = tok("surface");
      let s = `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="상권 영역 점수 레이더" style="max-width:520px">`;
      [25, 50, 75, 100].forEach((v) => { s += `<polygon class="gl" fill="none" points="${[0, 1, 2, 3].map((k) => pt(k, v).join(",")).join(" ")}"/><text class="tick" x="${cx + 4}" y="${cy - (R * v) / 100 + 12}">${v}</text>`; });
      KEYS.forEach((k, j) => {
        const [ex, ey] = pt(j, 100), [lx, ly] = pt(j, 118);
        s += `<line class="gl" x1="${cx}" y1="${cy}" x2="${ex}" y2="${ey}"/><text x="${lx}" y="${ly + 4}" text-anchor="${j === 1 ? "start" : j === 3 ? "end" : "middle"}" class="lbl" style="font-weight:600">${LONG[k]}</text>`;
      });
      const poly = (vals, color, width, fillOp) => {
        const ok = vals.map((v) => isNum(v));
        if (ok.every(Boolean)) return `<polygon points="${vals.map((v, k) => pt(k, v).join(",")).join(" ")}" fill="${color}" fill-opacity="${fillOp}" stroke="${color}" stroke-width="${width}" stroke-linejoin="round"/>`;
        let out = "";
        for (let k = 0; k < 4; k++) { const n = (k + 1) % 4; if (ok[k] && ok[n]) out += `<line x1="${pt(k, vals[k])[0]}" y1="${pt(k, vals[k])[1]}" x2="${pt(n, vals[n])[0]}" y2="${pt(n, vals[n])[1]}" stroke="${color}" stroke-width="${width}"/>`; }
        return out;
      };
      s += poly(KEYS.map((k) => med[k]), ink2, 1.5, 0);
      list.forEach((i, j) => {
        const x = c.by.get(i), vals = KEYS.map((k) => x[k]);
        s += poly(vals, cols[j], 2, 0.1);
        vals.forEach((v, k) => { if (isNum(v)) { const [px, py] = pt(k, v); s += `<circle cx="${px}" cy="${py}" r="4.5" fill="${cols[j]}" stroke="${surf}" stroke-width="2" data-tip="${esc(`${A.name[i]}\n${LONG[KEYS[k]]} ${s1f(v)}점 (중앙값 ${s1f(med[KEYS[k]])})`)}"/>`; } });
      });
      g.innerHTML = `<div class="radar-wrap"><div>${s}</svg></div><div class="table-wrap">${table([
        { k: "n", l: "상권", html: (v, x) => `<span class="sw" style="background:${x.c};width:10px;height:10px;display:inline-block;border-radius:2px;margin-right:6px"></span>${esc(v)}` },
        { k: "total", l: "종합", num: true, f: s1f }].concat(KEYS.map((k) => ({ k: k, l: SHORT[k], num: true, f: s1f }))),
        list.map((i, j) => Object.assign({ n: `${c.by.get(i).rank || "—"}. ${A.name[i]} (${A.gu[i]})`, c: cols[j] }, c.by.get(i))).concat([Object.assign({ n: "서울 같은 업종 중앙값", c: ink2, total: null }, med)]))}</div></div>`;
      $("v6l").innerHTML = list.map((i, j) => `<span><span class="sw" style="background:${cols[j]}"></span>${esc(A.name[i])}</span>`).join("") + `<span><span class="sw" style="background:${ink2};height:2px"></span>서울 같은 업종 중앙값</span>`;
      const best = list.map((i) => { const x = c.by.get(i), k = KEYS.filter((kk) => isNum(x[kk])).sort((a, b) => x[b] - x[a])[0]; return `${esc(A.name[i])}은(는) ${LONG[k]}(${s1f(x[k])})`; });
      const missing = list.filter((i) => KEYS.some((k) => !isNum(c.by.get(i)[k])));
      found("v6", `가장 강한 영역: ${best.join(", ")}. 종합 점수가 비슷해도 강점이 다릅니다.` + (missing.length ? ` 자료가 없는 영역은 선을 잇지 않았습니다(${missing.map((i) => esc(A.name[i])).join(", ")}).` : "") + " 경쟁과 수요는 둘 다 유동인구를 써서 순위상관이 0.47입니다.");
      $("v6t").innerHTML = "<p class=\"note\">위 표와 같습니다.</p>";
    }

    function drawV7() {
      const r = IND[state.industry], g = $("v7g");
      $("v7c").innerHTML = '<span class="note">뚜렷한 결과(5:0 · 4:1) 기준입니다. 3:2 경계 유형은 여기 넣지 않았습니다.</span>';
      if (!r.scored) {
        g.innerHTML = `<p class="empty">${esc(r.name)}은(는) 점수를 만들지 않아 비교할 수 없습니다. 사유: ${esc(r.reason)}</p>`;
        $("v7l").innerHTML = ""; $("v7t").innerHTML = "";
        found("v7", "점수가 있는 업종을 고르세요.");
        return;
      }
      const T = C.typeCompare(P, state.industry, P.step5.weights, 5), mine = state.profile ? state.profile.type : null;
      const twos = ["LE", "LP", "VE", "VP"], maxPool = Math.max(...twos.map((t) => T[t + "S"].pool), 1);
      const W = 900, lw = 150, rh = 28, Hh = 10 + rh * 4 + 26, x = lin(0, maxPool, lw, W - 80), c1 = tok("s1");
      let s = `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="상권 유형별 후보 상권 수">`;
      niceTicks(0, maxPool, 4).forEach((v) => { s += `<line class="gl" x1="${x(v)}" x2="${x(v)}" y1="8" y2="${Hh - 22}"/><text class="tick" x="${x(v)}" y="${Hh - 6}" text-anchor="middle">${nf(v)}</text>`; });
      twos.forEach((t, k) => {
        const y = 10 + k * rh, n = T[t + "S"].pool;
        s += `<text x="${lw - 10}" y="${y + rh / 2 + 3}" text-anchor="end" class="lbl">${t} 상권</text><rect x="${lw}" y="${y + 6}" width="${Math.max(0, x(n) - lw)}" height="${rh - 12}" rx="3" fill="${c1}" data-tip="${esc(`${t} 상권 중 ${r.name} 점수 대상 ${nf(n)}곳`)}"/>`;
        s += `<text x="${x(n) + 6}" y="${y + rh / 2 + 3}" class="tick">${nf(n)}곳</text>`;
      });
      s += "</svg>";
      const cards = TYPE_ORDER.map((t) => {
        const two = t.slice(0, 2), other = T[two + (t[2] === "S" ? "G" : "S")].top.map((x2) => x2.i), d = T[t], info = TYPES[t];
        return `<div class="mini"${t === mine ? ` style="box-shadow:inset 0 0 0 2px ${c1}"` : ""}><h4>${info["이모지"]} ${t} ${esc(info["이름"])}${t === mine ? ' <span class="badge match">내 유형</span>' : ""}</h4>` +
          `<div class="pool">${two} 상권 ${nf(d.pool)}곳 · ${t[2] === "S" ? "S 안정형" : "G 성장형"} 가중치</div><ol>` +
          d.top.map((x2) => `<li data-tip="${esc(`${areaLabel(x2.i)}\n종합 ${s1f(x2.total)} · 매출 ${s1f(x2.sales)} · 경쟁 ${s1f(x2.competition)} · 안정성 ${s1f(x2.stability)} · 수요 ${s1f(x2.demand)}`)}">${esc(A.name[x2.i])}${other.indexOf(x2.i) >= 0 ? '<span class="both">S·G 공통</span>' : ""}<span class="sc">${s1f(x2.total)}</span></li>`).join("") + "</ol></div>";
      }).join("");
      g.innerHTML = `<p class="note" style="margin-top:0">${esc(r.name)}: 상권 유형(두 글자)별 점수 대상 상권 수</p>${s}<div class="mini-grid" style="margin-top:12px">${cards}</div>`;
      $("v7l").innerHTML = `<span><span class="sw" style="background:${c1}"></span>후보 상권 수</span><span><span class="both" style="font-size:0.72rem;border:1px solid var(--axis);border-radius:4px;padding:0 4px">S·G 공통</span> 같은 두 글자의 S · G 상위 5곳에 모두 있음</span>`;
      const ov = twos.map((t) => { const a = T[t + "S"].top.map((x2) => x2.i), b = T[t + "G"].top.map((x2) => x2.i); return `${t} ${a.filter((i) => b.indexOf(i) >= 0).length}곳`; });
      found("v7", `${esc(r.name)}: S와 G 상위 5곳이 겹치는 수는 ${ov.join(" · ")}입니다. 후보는 앞 두 글자(L/V · E/P)가 정하고, S/G 가중치는 순서를 바꿉니다.`);
      $("v7t").innerHTML = table([{ k: "t", l: "창업자 유형" }, { k: "k", l: "순위", num: true }, { k: "n", l: "상권" }, { k: "total", l: "종합", num: true, f: s1f },
        { k: "sales", l: "매출", num: true, f: s1f }, { k: "competition", l: "경쟁", num: true, f: s1f }, { k: "stability", l: "안정성", num: true, f: s1f }, { k: "demand", l: "수요", num: true, f: s1f }],
        TYPE_ORDER.flatMap((t) => T[t].top.map((x2, k) => Object.assign({ t: t, k: k + 1, n: areaLabel(x2.i) }, x2))));
    }

    // ------------------------------------------------------------ 이동
    const RENDER = { s1: renderS1, s2: renderS2, s3: renderS3, s4: renderS4, s5: renderS5, s6: renderS6, s7: renderS7, s8: renderS8, s9: () => {}, s10: () => {} };
    function route() {
      const h = (location.hash || "#s1").slice(1);
      const page = PAGES.indexOf(h) >= 0 ? h : /^v[1-7]$/.test(h) ? "s8" : "s1";
      const changed = page !== state.page;
      state.page = page;
      PAGES.forEach((p) => { $("p-" + p).hidden = p !== page; });
      document.querySelectorAll("#nav a").forEach((a) => { if (a.getAttribute("href") === "#" + page) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
      RENDER[page]();
      if (page === "s8" && h !== page) { const el = $(h); if (el) el.scrollIntoView({ block: "start" }); }
      else if (changed) window.scrollTo(0, 0);
    }
    function refresh() { RENDER[state.page](); }

    window.addEventListener("hashchange", route);
    if (window.matchMedia) {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      const onScheme = () => { if (state.theme === "auto") refresh(); };
      if (mq.addEventListener) mq.addEventListener("change", onScheme); else if (mq.addListener) mq.addListener(onScheme);
    }
    initHeader();
    fillKeys();
    state.page = null;
    route();
    document.documentElement.setAttribute("data-ready", "1");
  }
})();
