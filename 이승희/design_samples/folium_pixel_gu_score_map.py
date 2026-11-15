# -*- coding: utf-8 -*-
"""
folium 픽셀 아트 자치구 점수 지도 샘플 (디자인 시안). 25개 자치구를 커피-음료 종합 점수 중앙값으로 칠하고,
구를 클릭하면 그 구로 확대해 구 안의 약 400m 점수 칸과 상위 상권을 보여 준다.

실행 (팀 저장소 루트에서):
    UV_PYTHON=3.12 uv run --project "이승희/step4_dashboard" --with folium --with shapely python "이승희/design_samples/folium_pixel_gu_score_map.py"
결과:
    이승희/design_samples/folium_pixel_gu_score_map_sample.html  (배경 지도 타일 없음. 글꼴만 인터넷)
필요한 파일: 같은 폴더의 seoul_gu_pixel.geojson (folium_pixel_gu_map.py가 만든 도트 구 모양과 한강)

색 기준
    서울 전체 화면: 구별 '점수 대상 상권의 종합 점수 중앙값'을 25개 구 안에서 5단계(각 5개 구)로 나눈 순위 색.
    구 상세 화면: 약 400m 칸 안 상권의 평균 종합 점수를 점수 자체 기준 5단계(35·45·55·65)로 칠한 색. 두 화면의 색 기준이 달라 범례도 바뀐다.
"""
import json
import sys
from pathlib import Path

import folium
import numpy as np
import pandas as pd
from branca.element import MacroElement
from jinja2 import Template
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCORES = REPO / "이승희" / "step4_dashboard" / "data" / "상권_업종_비교점수_2025.parquet"
GEO = REPO / "김지영" / "claude_dashboard" / "data" / "areas.geojson.json"
GU = HERE / "seoul_gu_pixel.geojson"
OUTSIDE = HERE / "outside_pixel.geojson"     # 서울 주변 시·군 도트 실루엣 (처음 한 번 원본에서 만들어 저장)
RAW_GEO = [REPO / "이승희" / "data" / "raw" / "geo" / "HangJeongDong_ver20251231.geojson",
           REPO.parents[1] / "PJT2-SpotFit" / "data" / "raw" / "geo" / "HangJeongDong_ver20251231.geojson"]
AROUND = (126.55, 37.28, 127.45, 37.86)    # 실루엣을 그릴 범위 (경도·위도)
OUTSIDE_FILL, OUTSIDE_LINE = "#E6DCC0", "#D6C9A6"
OUT = HERE / "folium_pixel_gu_score_map_sample.html"

INDUSTRY, INDUSTRY_NAME = "CS100010", "커피-음료"
CELL_LON, CELL_LAT = 0.0045, 0.0036          # 상세 칸 약 400m (구 도트 모양과 같은 격자)
INK, CREAM, CARD, RIVER = "#2B2A26", "#FBF3DC", "#FFFBEF", "#9EC3F2"
COLORS = ["#9FD3A8", "#3E9B5B", "#F4C430", "#5B8FE0", "#163F82"]   # 낮음 → 높음 (밝기도 함께 달라짐)
STEPS = [(0, 35, "35 미만"), (35, 45, "35~45"), (45, 55, "45~55"), (55, 65, "55~65"), (65, 101, "65 이상")]
NO_SCORE = "#CFC6AE"
PAD_OVERVIEW = {"paddingTopLeft": [20, 130], "paddingBottomRight": [300, 20]}
PIN = ('<svg width="30" height="39" viewBox="0 0 10 13" style="image-rendering:pixelated;shape-rendering:crispEdges" aria-hidden="true">'
       '<path fill="#2B2A26" d="M2 0h6v1H2zM1 1h8v1H1zM0 2h10v4H0zM1 6h8v2H1zM2 8h6v1H2zM3 9h4v1H3zM4 10h2v2H4z"></path>'
       '<path fill="#E5484D" d="M3 1h4v1H3zM2 2h6v1H2zM1 3h8v3H1zM2 6h6v1H2zM3 7h4v1H3zM4 8h2v1H4z"></path>'
       '<path fill="#FFFFFF" d="M4 3h2v1H4zM3 4h4v1H3zM4 5h2v1H4z"></path></svg>')


def step_color(score):
    if pd.isna(score):
        return NO_SCORE
    return next(COLORS[i] for i, (lo, hi, _) in enumerate(STEPS) if lo <= score < hi)


def outside_silhouettes():
    """서울 주변(경기·인천) 시·군을 같은 400m 격자의 도트 실루엣으로 만든다. 이름·점수 없이 모양만 쓴다."""
    if OUTSIDE.exists():
        return json.loads(OUTSIDE.read_text(encoding="utf-8"))["features"]
    import re
    from shapely.geometry import Point, box
    from shapely.prepared import prep

    raw = next((p for p in RAW_GEO if p.exists()), None)
    if raw is None:
        sys.exit("행정동 경계 원본(HangJeongDong_ver20251231.geojson)이 없습니다. 이승희/data/raw/geo/ 에 넣어 주세요.")
    area = box(*AROUND)
    groups = {}
    for f in json.loads(raw.read_text(encoding="utf-8"))["features"]:
        pr = f["properties"]
        if pr["sido"] == "11":
            continue
        geom = shape(f["geometry"])
        if not geom.intersects(area):
            continue
        # 인천은 하나로, 경기는 시·군 단위로 (고양시덕양구 → 고양시)
        key = "인천" if pr["sidonm"].startswith("인천") else re.match(r"^(.+?[시군])", pr["sggnm"]).group(1)
        groups.setdefault(key, []).append(geom)
    shapes = {k: prep(unary_union(v)) for k, v in groups.items()}
    cells = {k: [] for k in groups}
    x0, y0, x1, y1 = AROUND
    for cx in range(int(np.floor(x0 / CELL_LON)), int(np.floor(x1 / CELL_LON)) + 1):
        for cy in range(int(np.floor(y0 / CELL_LAT)), int(np.floor(y1 / CELL_LAT)) + 1):
            c = Point((cx + 0.5) * CELL_LON, (cy + 0.5) * CELL_LAT)
            k = next((k for k, s in shapes.items() if s.contains(c)), None)
            if k:
                cells[k].append(box(cx * CELL_LON, cy * CELL_LAT, (cx + 1) * CELL_LON, (cy + 1) * CELL_LAT))
    feats = [{"type": "Feature", "properties": {"name": k, "cells": len(v)}, "geometry": mapping(unary_union(v).buffer(0))}
             for k, v in sorted(cells.items()) if v]
    OUTSIDE.write_text(json.dumps({"type": "FeatureCollection", "source": raw.name, "features": feats}, ensure_ascii=False),
                       encoding="utf-8")
    return feats


def load():
    d = pd.read_parquet(SCORES, columns=["trdar_code", "industry_code", "trdar_name", "gu_name", "score_status", "score_total_default"])
    d = d.loc[d["industry_code"].eq(INDUSTRY)].copy()
    pts = pd.DataFrame([{k: f[k] for k in ("trdar_code", "lon", "lat")} for f in json.loads(GEO.read_text(encoding="utf-8"))])
    d = d.merge(pts, on="trdar_code", how="inner", validate="one_to_one")
    d["score"] = d["score_total_default"].where(d["score_status"].eq("점수 대상"))
    d["seoul_rank"] = d["score"].rank(ascending=False, method="min")
    d["cx"] = np.floor(d["lon"] / CELL_LON).astype(int)
    d["cy"] = np.floor(d["lat"] / CELL_LAT).astype(int)
    return d


def gu_summary(d):
    s = d.dropna(subset=["score"])
    g = s.groupby("gu_name").agg(n=("trdar_code", "size"), median=("score", "median"))
    best = s.loc[s.groupby("gu_name")["score"].idxmax(), ["gu_name", "trdar_name", "score"]].set_index("gu_name")
    g["best"] = best["trdar_name"] + " " + best["score"].round(0).astype(int).astype(str) + "점"
    g["cls"] = pd.qcut(g["median"].rank(method="first"), 5, labels=False)   # 25개 구를 5개씩 5단계로
    return g


def detail_data(d, gus, g):
    """구마다 상세 화면에 쓸 칸·상위 상권·확대 범위."""
    n_all = int(d["score"].notna().sum())
    out = {}
    for f in gus:
        name = f["properties"]["name"]
        x0, y0, x1, y1 = shape(f["geometry"]).bounds
        part = d.loc[d["gu_name"].eq(name)]
        cells = []
        for (cx, cy), c in part.groupby(["cx", "cy"]):
            s = c.dropna(subset=["score"])
            mean = s["score"].mean() if len(s) else np.nan
            best = f"{s.loc[s['score'].idxmax(), 'trdar_name']} {s['score'].max():.0f}점" if len(s) else "-"
            cells.append({"b": [[cy * CELL_LAT, cx * CELL_LON], [(cy + 1) * CELL_LAT, (cx + 1) * CELL_LON]],
                          "c": step_color(mean),
                          "t": f"<b>상권 {len(c)}곳</b> (점수 있음 {len(s)}곳)<br>평균 점수 {'-' if pd.isna(mean) else f'{mean:.0f}점'}<br>최고: {best}"})
        top = part.dropna(subset=["score"]).nlargest(5, "score")
        out[name] = {
            "bounds": [[y0, x0], [y1, x1]], "cells": cells,
            "n": int(g.loc[name, "n"]), "median": round(float(g.loc[name, "median"]), 1), "all": int(len(part)),
            "top": [{"name": r.trdar_name, "score": round(float(r.score), 1), "rank": int(r.seoul_rank)} for r in top.itertuples()],
            "seoul_n": n_all,
        }
    return out


class ClickDetail(MacroElement):
    """구를 클릭하면 확대·상세 칸·상세 상자, '서울 전체' 버튼으로 되돌리기."""
    _template = Template("""{% macro script(this, kwargs) %}{% raw %}
(function () {
  var map = __MAP__, gj = __GJ__, DETAIL = __DATA__, SEOUL = __SEOUL__, PAD = __PAD__;
  var layer = L.layerGroup().addTo(map);
  var panel = document.getElementById('gu-panel');
  var lgOverview = document.getElementById('legend-overview'), lgDetail = document.getElementById('legend-detail');
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function reset() {
    layer.clearLayers();
    gj.eachLayer(function (l) { l.setStyle({fillOpacity: 1, weight: 2.5, color: '#FFFFFF'}); });
    panel.style.display = 'none'; lgOverview.style.display = 'flex'; lgDetail.style.display = 'none';
    map.fitBounds(SEOUL, PAD);
  }
  function show(name) {
    var d = DETAIL[name]; if (!d) { return; }
    layer.clearLayers();
    gj.eachLayer(function (l) {
      var on = l.feature.properties.name === name;
      l.setStyle(on ? {fillOpacity: 0.12, weight: 4, color: '#2B2A26'} : {fillOpacity: 0.3, weight: 2.5, color: '#FFFFFF'});
    });
    d.cells.forEach(function (c) {
      L.rectangle(c.b, {color: '#2B2A26', weight: 1, fillColor: c.c, fillOpacity: 0.95})
        .bindTooltip(c.t, {className: 'px-tip', sticky: true}).addTo(layer);
    });
    var rows = d.top.map(function (t, i) {
      return '<li><b>' + (i + 1) + '</b><span>' + esc(t.name) + '</span><em>' + t.score.toFixed(1) + '</em><small>서울 ' + t.rank + '위</small></li>';
    }).join('');
    panel.innerHTML =
      '<button type="button" class="px-back" onclick="spotfitReset()">← 서울 전체</button>' +
      '<h2>' + esc(name) + '</h2>' +
      '<div class="px-stats"><div><small>점수 상권</small><b>' + d.n + '곳</b></div><div><small>점수 중앙값</small><b>' + d.median.toFixed(1) + '</b></div></div>' +
      '<div class="px-sub">이 구의 ' + 'STEP 4 점수 상위 5곳 (서울 같은 업종 ' + d.seoul_n + '곳 중 순위)</div>' +
      '<ol class="px-top">' + rows + '</ol>' +
      '<div class="px-note">칸 = 약 400m · 칸 안 상권의 평균 점수. 칸에 마우스를 올리면 상권 수와 최고 상권이 나옵니다.</div>';
    panel.style.display = 'block'; lgOverview.style.display = 'none'; lgDetail.style.display = 'flex';
    map.fitBounds(d.bounds, {paddingTopLeft: [360, 40], paddingBottomRight: [40, 40]});
  }
  gj.eachLayer(function (l) {
    l.on('click', function (e) { L.DomEvent.stopPropagation(e); show(l.feature.properties.name); });
  });
  window.spotfitReset = reset;
})();
{% endraw %}{% endmacro %}""")

    def __init__(self, map_obj, gj, data, seoul):
        super().__init__()
        self._js = {"__MAP__": map_obj.get_name(), "__GJ__": gj.get_name(), "__DATA__": json.dumps(data, ensure_ascii=False),
                    "__SEOUL__": json.dumps(seoul), "__PAD__": json.dumps(PAD_OVERVIEW)}

    def render(self, **kwargs):
        text = str(self._template.module.__dict__["script"](self, kwargs))   # 템플릿의 script 매크로 내용
        for k, v in self._js.items():
            text = text.replace(k, v)
        figure = self.get_root()
        figure.script.add_child(folium.Element(text), name=self.get_name())


def main():
    fc = json.loads(GU.read_text(encoding="utf-8"))
    gus = [f for f in fc["features"] if f["properties"]["kind"] == "gu"]
    river = next(f for f in fc["features"] if f["properties"]["kind"] == "river")
    d = load()
    g = gu_summary(d)
    for f in gus:
        r = g.loc[f["properties"]["name"]]
        f["properties"].update({"median": round(float(r["median"]), 1), "n": int(r["n"]), "best": r["best"],
                                "color": COLORS[int(r["cls"])]})

    seoul = unary_union([shape(f["geometry"]) for f in gus])
    x0, y0, x1, y1 = seoul.bounds
    seoul_bounds = [[y0, x0], [y1, x1]]
    m = folium.Map(location=[37.565, 126.985], zoom_start=12, min_zoom=10, max_zoom=14, tiles=None, zoom_snap=0.25)
    m.fit_bounds(seoul_bounds, padding_top_left=PAD_OVERVIEW["paddingTopLeft"], padding_bottom_right=PAD_OVERVIEW["paddingBottomRight"])

    # 서울 밖: 경기·인천 시·군의 도트 실루엣 (이름·점수 없이 모양만, 시·군 사이는 옅은 선)
    folium.GeoJson({"type": "FeatureCollection", "features": outside_silhouettes()}, name="서울 밖", interactive=False,
                   style_function=lambda f: {"fillColor": OUTSIDE_FILL, "fillOpacity": 1, "color": OUTSIDE_LINE, "weight": 1.5}).add_to(m)

    ring = [(y, x) for x, y in seoul.exterior.coords]
    folium.PolyLine([(y - 0.0012, x + 0.0015) for y, x in ring], color="#F4C430", weight=7, interactive=False).add_to(m)
    gj = folium.GeoJson(
        {"type": "FeatureCollection", "features": gus}, name="자치구",
        style_function=lambda f: {"fillColor": f["properties"]["color"], "fillOpacity": 1, "color": "#FFFFFF", "weight": 2.5},
        tooltip=folium.GeoJsonTooltip(fields=["name", "median", "n", "best"], aliases=["", "점수 중앙값", "점수 상권 수", "최고 상권"],
                                      class_name="px-tip"),
    ).add_to(m)
    folium.GeoJson(river, interactive=False,
                   style_function=lambda f: {"fillColor": RIVER, "fillOpacity": 1, "color": RIVER, "weight": 0.5}).add_to(m)
    folium.PolyLine(ring, color=INK, weight=4, interactive=False).add_to(m)

    for f in gus:
        p = shape(f["geometry"]).representative_point()
        pr = f["properties"]
        html = f'<div class="gu-label">{pr["name"]}<span>{pr["median"]:.0f}</span></div>'
        folium.Marker([p.y, p.x], icon=folium.DivIcon(html=html, icon_size=(90, 22), icon_anchor=(45, 11), class_name="gu-label-wrap"),
                      interactive=False).add_to(m)

    top = d.dropna(subset=["score"]).nlargest(10, "score")
    for i, r in enumerate(top.itertuples(), start=1):
        folium.Marker([r.lat, r.lon], icon=folium.DivIcon(html=f'<div style="position:relative">{PIN}<span class="px-rank">{i}</span></div>',
                                                         icon_size=(30, 39), icon_anchor=(15, 39), class_name="px-pin"),
                      tooltip=folium.Tooltip(f"<b>{i}위 {r.trdar_name}</b> · {r.gu_name}<br>종합 {r.score:.1f}점", class_name="px-tip")).add_to(m)

    ClickDetail(m, gj, detail_data(d, gus, g), seoul_bounds).add_to(m)

    ranges = g.groupby("cls")["median"].agg(["min", "max"])
    legend_overview = "".join(
        f'<div class="lg-row"><span style="background:{COLORS[c]}"></span>{ranges.loc[c, "min"]:.1f} ~ {ranges.loc[c, "max"]:.1f}점</div>'
        for c in range(4, -1, -1))
    legend_detail = "".join(f'<div class="lg-row"><span style="background:{COLORS[i]}"></span>{STEPS[i][2]}</div>' for i in range(4, -1, -1))
    pin_small = PIN.replace('width="30" height="39"', 'width="12" height="16"')
    pin_row = f'<div class="lg-row" style="margin-top:4px"><i>{pin_small}</i>상위 10곳 상권</div>'
    m.get_root().header.add_child(folium.Element(f"""
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap">
<style>
  html, body {{ background: {CREAM}; }}
  .leaflet-container {{ background: {CREAM} !important; font-family: 'Malgun Gothic', '맑은 고딕', 'Noto Sans KR', sans-serif; }}
  .leaflet-overlay-pane svg path {{ shape-rendering: crispEdges; }}
  .leaflet-interactive {{ cursor: pointer; }}
  .leaflet-interactive:focus {{ outline: none; }}   /* 클릭한 구 둘레에 브라우저가 그리는 사각형 테두리 끄기 */
  .gu-label {{ display: inline-flex; gap: 5px; align-items: center; padding: 1px 6px; background: {CARD}; color: {INK};
    border: 2px solid {INK}; box-shadow: 2px 2px 0 {INK}; font-weight: 700; font-size: 12px; white-space: nowrap; pointer-events: none; }}
  .gu-label span {{ font-family: 'Press Start 2P', monospace; font-size: 9px; color: #1F5FC4; }}
  .gu-label-wrap {{ display: flex; justify-content: center; align-items: center; pointer-events: none; }}
  .px-rank {{ position: absolute; left: 22px; top: -6px; min-width: 20px; padding: 3px 4px; background: {INK}; color: #fff;
    font-family: 'Press Start 2P', monospace; font-size: 9px; text-align: center; }}
  .leaflet-tooltip.px-tip {{ background: {CARD}; color: {INK}; border: 3px solid {INK}; border-radius: 0; box-shadow: 3px 3px 0 {INK};
    font-size: 13px; padding: 6px 10px; }}
  .leaflet-tooltip.px-tip::before {{ display: none; }}
  .leaflet-bar {{ border: 3px solid {INK} !important; border-radius: 0 !important; box-shadow: 3px 3px 0 {INK}; }}
  .leaflet-bar a {{ border-radius: 0 !important; color: {INK}; background: {CARD}; font-family: 'Press Start 2P', monospace; font-size: 14px; }}
  .px-box {{ position: fixed; z-index: 1000; background: {CARD}; color: {INK}; border: 4px solid {INK}; box-shadow: 6px 6px 0 {INK}; }}
  .lg-row {{ display: flex; align-items: center; gap: 8px; }}
  .lg-row span {{ width: 16px; height: 16px; border: 2px solid {INK}; display: inline-block; box-sizing: border-box; }}
  .lg-row i {{ display: inline-block; width: 16px; text-align: center; font-style: normal; }}
  #gu-panel {{ display: none; top: 150px; left: 16px; width: 300px; padding: 14px 16px; font-size: 14px; max-height: calc(100vh - 190px); overflow-y: auto; }}
  #gu-panel h2 {{ margin: 8px 0 8px; font-size: 22px; color: #1F5FC4; }}
  .px-back {{ min-height: 40px; padding: 0 12px; font: inherit; font-weight: 700; color: {INK}; background: #F4C430;
    border: 3px solid {INK}; box-shadow: 3px 3px 0 {INK}; cursor: pointer; }}
  .px-stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; }}
  .px-stats div {{ background: #FFF3C4; border: 2px solid {INK}; padding: 4px 8px; }}
  .px-stats small {{ display: block; font-size: 12px; color: #5A5446; }}
  .px-stats b {{ font-size: 18px; }}
  .px-sub {{ font-size: 12px; color: #5A5446; margin-bottom: 4px; }}
  .px-top {{ list-style: none; margin: 0 0 10px; padding: 0; display: flex; flex-direction: column; gap: 6px; }}
  .px-top li {{ display: grid; grid-template-columns: 20px minmax(0, 1fr) auto; grid-template-rows: auto auto; column-gap: 8px;
    padding: 6px 8px; background: #FFFFFF; border: 2px solid {INK}; }}
  .px-top li b {{ grid-row: span 2; font-family: 'Press Start 2P', monospace; font-size: 11px; align-self: center; }}
  .px-top li span {{ font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .px-top li em {{ font-style: normal; font-weight: 700; color: #1F5FC4; }}
  .px-top li small {{ grid-column: 2 / 4; font-size: 12px; color: #5A5446; }}
  .px-note {{ font-size: 12px; color: #5A5446; }}
</style>"""))
    m.get_root().html.add_child(folium.Element(f"""
<div class="px-box" style="top:16px;left:64px;padding:12px 16px">
  <div style="font-family:'Press Start 2P',monospace;font-size:20px;color:#1F5FC4;text-shadow:3px 3px 0 #F4C430">SPOTFIT</div>
  <div style="font-size:14px;font-weight:700;margin-top:6px">{INDUSTRY_NAME} · 자치구별 종합 점수</div>
  <div style="font-size:12px;color:#5A5446">구를 클릭하면 확대해서 구 안을 자세히 봅니다</div>
</div>
<div id="gu-panel" class="px-box" aria-live="polite"></div>
<div class="px-box" style="bottom:24px;right:16px;padding:12px 14px;font-size:13px">
  <div id="legend-overview" style="display:flex;flex-direction:column;gap:6px">
    <b>구별 점수 중앙값 (구 5개씩 5단계)</b>
    {legend_overview}
    {pin_row}
    <div style="font-size:11px;color:#5A5446">색은 구끼리의 순위 · 구 안의 차이는 클릭해서 보기</div>
  </div>
  <div id="legend-detail" style="display:none;flex-direction:column;gap:6px">
    <b>칸 평균 점수 (약 400m 칸)</b>
    {legend_detail}
    <div class="lg-row"><span style="background:{NO_SCORE}"></span>점수 없음 (점포 5개 미만 등)</div>
    {pin_row}
    <div style="font-size:11px;color:#5A5446">상세 화면은 점수 자체 기준 색 (서울 전체 화면과 기준이 다름)</div>
  </div>
</div>"""))
    m.save(OUT)
    print(f"[완료] {OUT.relative_to(REPO).as_posix()} · 구 {len(gus)}개, 중앙값 {g['median'].min():.1f}~{g['median'].max():.1f}")


if __name__ == "__main__":
    main()
