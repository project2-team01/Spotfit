# -*- coding: utf-8 -*-
"""
folium 픽셀 아트 지도 샘플 (디자인 시안). 커피-음료 STEP 4 종합 점수를 정사각형 격자(도트)로 칠한다.

실행 (팀 저장소 루트에서, folium·shapely는 이번 실행에만 붙여 씀):
    UV_PYTHON=3.12 uv run --project "이승희/step4_dashboard" --with folium --with shapely python "이승희/design_samples/folium_pixel_map.py"
    처음 한 번은 서울 경계 원본(행정동 경계 geojson)이 필요하고, 만든 테두리는 seoul_pixel_outline.geojson 에 저장해 다음부터 씀
결과:
    이승희/design_samples/folium_pixel_map_sample.html  (브라우저로 열기, 배경 지도는 인터넷 필요)

픽셀 느낌을 내는 방법
    1. 배경 타일: 2단계 낮은 해상도의 타일을 4배로 키우고(tileSize 1024, zoomOffset -2) image-rendering: pixelated 로 각지게 그린다.
    2. 상권: 다각형 대신 약 400m 정사각형 격자로 모아 칸마다 점수 색을 칠한다 (칸 안 상권 평균 점수, 5단계 색).
    3. 상위 10곳: 도트 핀 + 도트 글꼴 번호. 범례·말풍선은 샘플 디자인과 같은 굵은 테두리·각진 그림자.
"""
import json
import sys
from pathlib import Path

import folium
import numpy as np
import pandas as pd
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union
from shapely.prepared import prep

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCORES = REPO / "이승희" / "step4_dashboard" / "data" / "상권_업종_비교점수_2025.parquet"
GEO = REPO / "김지영" / "claude_dashboard" / "data" / "areas.geojson.json"
# 칸 크기 배율: 기본 1 (약 400m). 예) python folium_pixel_map.py 3 → 약 1.2km 칸, 파일 이름에 grid3x가 붙음
MULT = int(sys.argv[1]) if len(sys.argv) > 1 else 1
OUT = HERE / ("folium_pixel_map_sample.html" if MULT == 1 else f"folium_pixel_map_grid{MULT}x_sample.html")
# 서울 경계: 행정동 경계 원본(통계청 행정동 경계, 2025-12-31)에서 한 번 만들어 작은 파일로 저장해 두고 다음부터 그 파일을 쓴다
OUTLINE = HERE / "seoul_pixel_outline.geojson"
GU = HERE / "seoul_gu_pixel.geojson"     # 자치구 도트 모양 (folium_pixel_gu_map.py가 만든 것, 같은 격자)
RAW_GEO = [REPO / "이승희" / "data" / "raw" / "geo" / "HangJeongDong_ver20251231.geojson",
           REPO.parents[1] / "PJT2-SpotFit" / "data" / "raw" / "geo" / "HangJeongDong_ver20251231.geojson"]

INDUSTRY = "CS100010"          # 커피-음료
BASE_LON, BASE_LAT = 0.0045, 0.0036   # 기본 격자 한 칸 (서울 위도에서 약 400m × 400m). 서울·자치구 경계는 이 칸에 맞춤
CELL_LON, CELL_LAT = BASE_LON * MULT, BASE_LAT * MULT   # 점수 칸
INK, CREAM, CARD = "#2B2A26", "#FBF3DC", "#FFFBEF"
# 점수 5단계 색: 낮음(초록) → 중간(노랑) → 높음(파랑). 밝기도 함께 달라서 색약에도 구분된다
STEPS = [(0, 35, "#9FD3A8", "35 미만"), (35, 45, "#3E9B5B", "35~45"), (45, 55, "#F4C430", "45~55"),
         (55, 65, "#5B8FE0", "55~65"), (65, 101, "#163F82", "65 이상")]
NO_SCORE = "#CFC6AE"
CELL_TEXT = f"{400 * MULT}m" if MULT * 400 < 1000 else f"{400 * MULT / 1000:.1f}km"


def color_for(score):
    if pd.isna(score):
        return NO_SCORE
    return next(c for lo, hi, c, _ in STEPS if lo <= score < hi)


def load():
    d = pd.read_parquet(SCORES, columns=["trdar_code", "industry_code", "trdar_name", "gu_name", "score_status", "score_total_default"])
    d = d.loc[d["industry_code"].eq(INDUSTRY)]
    g = pd.DataFrame([{k: f[k] for k in ("trdar_code", "lon", "lat")} for f in json.loads(GEO.read_text(encoding="utf-8"))])
    d = d.merge(g, on="trdar_code", how="inner", validate="one_to_one")
    d["score"] = d["score_total_default"].where(d["score_status"].eq("점수 대상"))
    d["cx"] = np.floor(d["lon"] / CELL_LON).astype(int)
    d["cy"] = np.floor(d["lat"] / CELL_LAT).astype(int)
    return d


def seoul_outline():
    """서울 경계를 점수 격자와 같은 칸에 맞춘 계단 모양 다각형으로 만든다. 칸 가운데가 서울 안이면 서울 칸."""
    if OUTLINE.exists():
        return shape(json.loads(OUTLINE.read_text(encoding="utf-8"))["features"][0]["geometry"])
    raw = next((p for p in RAW_GEO if p.exists()), None)
    if raw is None:
        sys.exit("서울 경계 원본(HangJeongDong_ver20251231.geojson)이 없습니다. 이승희/data/raw/geo/ 에 넣어 주세요.")
    feats = json.loads(raw.read_text(encoding="utf-8"))["features"]
    seoul = unary_union([shape(f["geometry"]) for f in feats if f["properties"].get("sido") == "11"])
    inside = prep(seoul)
    x0, y0, x1, y1 = seoul.bounds
    squares = []
    for cx in range(int(np.floor(x0 / BASE_LON)), int(np.floor(x1 / BASE_LON)) + 1):
        for cy in range(int(np.floor(y0 / BASE_LAT)), int(np.floor(y1 / BASE_LAT)) + 1):
            sq = box(cx * BASE_LON, cy * BASE_LAT, (cx + 1) * BASE_LON, (cy + 1) * BASE_LAT)
            if inside.contains(sq.centroid):
                squares.append(sq)
    pixel = unary_union(squares).buffer(0)
    if pixel.geom_type == "MultiPolygon":            # 떨어진 작은 칸이 생기면 가장 큰 덩어리만 쓴다
        pixel = max(pixel.geoms, key=lambda g: g.area)
    OUTLINE.write_text(json.dumps({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"name": "서울특별시", "source": raw.name, "cell_deg": [BASE_LON, BASE_LAT], "cells": len(squares)},
        "geometry": mapping(pixel)}]}, ensure_ascii=False), encoding="utf-8")
    return pixel


def cells(d):
    rows = []
    for (cx, cy), g in d.groupby(["cx", "cy"]):
        s = g.dropna(subset=["score"])
        best = s.loc[s["score"].idxmax()] if len(s) else None
        rows.append({
            "cx": cx, "cy": cy, "n": len(g), "n_scored": len(s),
            "mean": s["score"].mean() if len(s) else np.nan,
            "best": f"{best['trdar_name']} {best['score']:.0f}점" if best is not None else "-",
        })
    return pd.DataFrame(rows)


PIN = ('<svg width="30" height="39" viewBox="0 0 10 13" style="image-rendering:pixelated;shape-rendering:crispEdges" aria-hidden="true">'
       '<path fill="#2B2A26" d="M2 0h6v1H2zM1 1h8v1H1zM0 2h10v4H0zM1 6h8v2H1zM2 8h6v1H2zM3 9h4v1H3zM4 10h2v2H4z"></path>'
       '<path fill="#E5484D" d="M3 1h4v1H3zM2 2h6v1H2zM1 3h8v3H1zM2 6h6v1H2zM3 7h4v1H3zM4 8h2v1H4z"></path>'
       '<path fill="#FFFFFF" d="M4 3h2v1H4zM3 4h4v1H3zM4 5h2v1H4z"></path></svg>')

CSS = f"""
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap">
<style>
  html, body {{ background: {CREAM}; }}
  .leaflet-container {{ background: {CREAM}; font-family: 'Malgun Gothic', '맑은 고딕', 'Noto Sans KR', sans-serif; }}
  /* 1) 배경 타일을 각지게: 낮은 해상도 타일을 키울 때 부드럽게 번지지 않게 */
  .pixel-tiles img.leaflet-tile {{ image-rendering: pixelated; image-rendering: crisp-edges;
    filter: sepia(0.45) saturate(1.35) hue-rotate(-8deg) brightness(1.02) contrast(1.05); }}
  /* 격자 칸 테두리도 흐리지 않게 */
  .leaflet-overlay-pane svg path {{ shape-rendering: crispEdges; }}
  /* 말풍선: 굵은 테두리 + 각진 그림자 */
  .leaflet-tooltip.px-tip {{ background: {CARD}; color: {INK}; border: 3px solid {INK}; border-radius: 0;
    box-shadow: 3px 3px 0 {INK}; font-size: 13px; line-height: 1.5; padding: 6px 10px; }}
  .leaflet-tooltip.px-tip::before {{ display: none; }}
  /* 확대·축소 버튼 */
  .leaflet-bar {{ border: 3px solid {INK} !important; border-radius: 0 !important; box-shadow: 3px 3px 0 {INK}; }}
  .leaflet-bar a {{ border-radius: 0 !important; color: {INK}; background: {CARD}; font-family: 'Press Start 2P', monospace; font-size: 14px; }}
  .px-box {{ background: {CARD}; color: {INK}; border: 4px solid {INK}; box-shadow: 6px 6px 0 {INK}; }}
  .gu-label {{ display: inline-block; padding: 1px 6px; background: {CARD}; color: {INK}; border: 2px solid {INK};
    box-shadow: 2px 2px 0 {INK}; font-weight: 700; font-size: 12px; line-height: 1.4; white-space: nowrap; pointer-events: none; }}
  .gu-label-wrap {{ display: flex; justify-content: center; align-items: center; }}
  .px-rank {{ position: absolute; left: 22px; top: -6px; min-width: 20px; padding: 3px 4px; background: {INK}; color: #fff;
    font-family: 'Press Start 2P', monospace; font-size: 9px; text-align: center; }}
</style>
"""


def overlay_html(c):
    legend = "".join(
        f'<div style="display:flex;align-items:center;gap:8px"><span style="width:16px;height:16px;background:{col};border:2px solid {INK};display:inline-block"></span>{label}</div>'
        for _, _, col, label in STEPS)
    return f"""
<div class="px-box" style="position:fixed;top:16px;left:64px;z-index:1000;padding:12px 16px">
  <div style="font-family:'Press Start 2P',monospace;font-size:20px;color:#1F5FC4;text-shadow:3px 3px 0 #F4C430">SPOTFIT</div>
  <div style="font-size:14px;font-weight:700;margin-top:6px">커피-음료 · 종합 점수 도트 지도</div>
  <div style="font-size:12px;color:#5A5446">한 칸 = 약 {CELL_TEXT} · 칸 안 상권의 평균 점수</div>
</div>
<div class="px-box" style="position:fixed;bottom:24px;left:16px;z-index:1000;padding:12px 14px;font-size:13px;display:flex;flex-direction:column;gap:6px">
  <b>종합 점수 (평균)</b>
  {legend}
  <div style="display:flex;align-items:center;gap:8px"><span style="width:16px;height:16px;background:{NO_SCORE};border:2px solid {INK};display:inline-block"></span>점수 없음 (점포 5개 미만 등)</div>
  <div style="display:flex;align-items:center;gap:8px;margin-top:4px"><span style="display:inline-block;width:16px;text-align:center">{PIN.replace('width="30" height="39"', 'width="12" height="16"')}</span>상위 10곳 (번호 = 순위)</div>
  <div style="display:flex;align-items:center;gap:8px"><span style="width:16px;height:4px;background:{INK};box-shadow:1px 2px 0 #F4C430;display:inline-block"></span>서울 경계 (격자에 맞춘 계단 모양)</div>
  <div style="display:flex;align-items:center;gap:8px"><span style="width:16px;height:3px;background:#FFFFFF;border:2px solid {INK};display:inline-block"></span>자치구 경계 · 이름표</div>
  <div style="display:flex;align-items:center;gap:8px"><span style="width:16px;height:16px;background:#F3EEDD;border:2px dashed #8C846F;box-sizing:border-box;display:inline-block"></span>서울 밖 (흐리게)</div>
  <div style="font-size:11px;color:#5A5446;margin-top:2px">격자 {c['n']:,}칸 · 점수 있는 칸 {c['scored']:,}칸</div>
</div>
"""


def main():
    d = load()
    c = cells(d)
    m = folium.Map(location=[37.555, 126.99], zoom_start=12, min_zoom=11, max_zoom=13, tiles=None, control_scale=False,
                   prefer_canvas=False)
    # 1) 픽셀 배경 (Esri 회색 지도, API 키 필요 없음): 2단계 낮은 줌의 타일(256px)을 1024px로 키움 → 한 점이 4배
    #    도트가 너무 커지지 않게 확대는 11~13까지만
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors", name="pixel base",
        tile_size=1024, zoom_offset=-2, className="pixel-tiles", max_zoom=15,
    ).add_to(m)

    # 서울 밖(경기도·인천)은 크림색으로 덮어 흐리게. 큰 사각형에서 서울 모양을 구멍으로 뺀다
    seoul = seoul_outline()
    ring = [(y, x) for x, y in seoul.exterior.coords]
    outer = [(36.9, 126.2), (38.3, 126.2), (38.3, 127.8), (36.9, 127.8)]
    folium.Polygon(locations=[outer, ring], stroke=False, fill=True, fill_color=CREAM, fill_opacity=0.62,
                   interactive=False).add_to(m)

    # 2) 정사각형 격자 칸
    for r in c.itertuples():
        lon0, lat0 = r.cx * CELL_LON, r.cy * CELL_LAT
        tip = (f"<b>상권 {r.n}곳</b> (점수 있음 {r.n_scored}곳)<br>평균 점수 "
               + ("-" if pd.isna(r.mean) else f"{r.mean:.0f}점") + f"<br>최고: {r.best}")
        folium.Rectangle(
            bounds=[[lat0, lon0], [lat0 + CELL_LAT, lon0 + CELL_LON]],
            color=INK, weight=1, fill=True, fill_color=color_for(r.mean), fill_opacity=0.92,
            tooltip=folium.Tooltip(tip, class_name="px-tip", sticky=True),
        ).add_to(m)

    # 자치구 경계(흰 선)와 이름: 같은 격자로 만든 도트 구 모양을 겹친다
    if not GU.exists():
        import folium_pixel_gu_map                      # 같은 폴더의 자치구 지도 코드로 한 번 만든다
        folium_pixel_gu_map.build()
    gus = [f for f in json.loads(GU.read_text(encoding="utf-8"))["features"] if f["properties"]["kind"] == "gu"]
    # 흰 선만 쓰면 바탕 지도의 흰 도로와 섞여서, 검은 선(굵게) 위에 흰 선(가늘게)을 겹쳐 테두리 있는 선으로 그린다
    gu_fc = {"type": "FeatureCollection", "features": gus}
    folium.GeoJson(gu_fc, name="자치구 경계 (바깥)", interactive=False,
                   style_function=lambda f: {"fill": False, "color": INK, "weight": 5, "opacity": 0.85}).add_to(m)
    folium.GeoJson(gu_fc, name="자치구 경계", interactive=False,
                   style_function=lambda f: {"fill": False, "color": "#FFFFFF", "weight": 2.5, "opacity": 1}).add_to(m)

    # 서울 경계: 격자에 맞춘 계단 모양 굵은 선 + 오른쪽 아래로 비낀 노란 그림자 (샘플의 각진 그림자와 같은 느낌)
    shadow = [(y - 0.0010, x + 0.0012) for y, x in ring]
    folium.PolyLine(shadow, color="#F4C430", weight=5, opacity=1, line_cap="square", line_join="miter", interactive=False).add_to(m)
    folium.PolyLine(ring, color=INK, weight=5, opacity=1, line_cap="square", line_join="miter",
                    tooltip=folium.Tooltip("서울특별시 경계", class_name="px-tip")).add_to(m)
    for lat, lon in [(37.715, 126.83), (37.43, 126.80), (37.66, 127.20), (37.43, 127.15)]:
        if not seoul.contains(shape({"type": "Point", "coordinates": [lon, lat]})):
            folium.Marker([lat, lon], icon=folium.DivIcon(
                html='<div style="display:inline-block;padding:2px 8px;background:#FFFBEF;border:2px solid #8C846F;color:#5A5446;'
                     'font-size:13px;font-weight:700;white-space:nowrap">경기도</div>',
                icon_size=(60, 24), icon_anchor=(30, 12), class_name="px-label")).add_to(m)

    # 구 이름 (핀보다 먼저 그려 핀이 위에 오게)
    for f in gus:
        p = shape(f["geometry"]).representative_point()
        folium.Marker([p.y, p.x], icon=folium.DivIcon(html=f'<div class="gu-label">{f["properties"]["name"]}</div>',
                                                     icon_size=(70, 18), icon_anchor=(35, 9), class_name="gu-label-wrap")).add_to(m)

    # 3) 상위 10곳 도트 핀
    top = d.dropna(subset=["score"]).nlargest(10, "score")
    for i, r in enumerate(top.itertuples(), start=1):
        html = f'<div style="position:relative">{PIN}<span class="px-rank">{i}</span></div>'
        folium.Marker(
            [r.lat, r.lon], icon=folium.DivIcon(html=html, icon_size=(30, 39), icon_anchor=(15, 39), class_name="px-pin"),
            tooltip=folium.Tooltip(f"<b>{i}위 {r.trdar_name}</b> · {r.gu_name}<br>종합 {r.score:.1f}점", class_name="px-tip"),
        ).add_to(m)

    m.get_root().header.add_child(folium.Element(CSS))
    m.get_root().html.add_child(folium.Element(overlay_html({"n": len(c), "scored": int(c["n_scored"].gt(0).sum())})))
    m.save(OUT)
    print(f"[완료] {OUT.relative_to(REPO).as_posix()}")
    print(f"       상권 {len(d):,}곳 → 격자 {len(c):,}칸 (점수 있는 칸 {int(c['n_scored'].gt(0).sum()):,}칸), 상위 10곳 핀")


if __name__ == "__main__":
    main()
