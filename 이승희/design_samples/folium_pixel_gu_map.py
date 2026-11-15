# -*- coding: utf-8 -*-
"""
folium 픽셀 아트 자치구 지도 샘플 (디자인 시안). 서울 25개 자치구를 파란 도트로 칠하고, 구 사이는 흰 선, 구 이름은 흰 글씨, 한강은 연한 파란 도트.

실행 (팀 저장소 루트에서, folium·shapely는 이번 실행에만 붙여 씀):
    UV_PYTHON=3.12 uv run --project "이승희/step4_dashboard" --with folium --with shapely python "이승희/design_samples/folium_pixel_gu_map.py"
결과:
    이승희/design_samples/folium_pixel_gu_map_sample.html  (배경 지도 타일을 쓰지 않아 인터넷 없이도 열림. 글꼴만 인터넷)

만드는 방법
    1. 행정동 경계(통계청, 2025-12-31)에서 서울 행정동을 자치구별로 합친다.
    2. 약 400m 정사각형 격자를 만들고, 칸 가운데가 들어 있는 자치구에 그 칸을 준다 → 자치구마다 계단 모양 도트 다각형.
    3. 한강: 한강 북쪽 구(마포·용산·성동·광진)와 남쪽 구(강서·영등포·동작·서초·강남·송파·강동)가 맞닿는 경계선이
       강 한가운데를 지나므로, 그 선이 지나가는 칸을 한강 칸으로 칠한다. (서울 밖으로 이어지는 양 끝은 그리지 않음)
    처음 한 번은 행정동 경계 원본이 필요하고, 만든 도트 다각형은 seoul_gu_pixel.geojson 에 저장해 다음부터 쓴다.
"""
import json
import sys
from pathlib import Path

import folium
import numpy as np
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union
from shapely.prepared import prep

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "folium_pixel_gu_map_sample.html"
CACHE = HERE / "seoul_gu_pixel.geojson"
RAW_GEO = [REPO / "이승희" / "data" / "raw" / "geo" / "HangJeongDong_ver20251231.geojson",
           REPO.parents[1] / "PJT2-SpotFit" / "data" / "raw" / "geo" / "HangJeongDong_ver20251231.geojson"]

CELL_LON, CELL_LAT = 0.0045, 0.0036          # 점수 도트 지도와 같은 격자 (약 400m)
NORTH = ["마포구", "용산구", "성동구", "광진구"]
SOUTH = ["강서구", "영등포구", "동작구", "서초구", "강남구", "송파구", "강동구"]
BLUE, WHITE, RIVER, CREAM, INK = "#2D6BD0", "#FFFFFF", "#9EC3F2", "#FBF3DC", "#2B2A26"


def build():
    """자치구별 도트 다각형과 한강 칸을 만든다 (원본이 있을 때 한 번만)."""
    raw = next((p for p in RAW_GEO if p.exists()), None)
    if raw is None:
        sys.exit("행정동 경계 원본(HangJeongDong_ver20251231.geojson)이 없습니다. 이승희/data/raw/geo/ 에 넣어 주세요.")
    feats = [f for f in json.loads(raw.read_text(encoding="utf-8"))["features"] if f["properties"].get("sido") == "11"]
    names = sorted({f["properties"]["sggnm"] for f in feats})
    gu = {n: unary_union([shape(f["geometry"]) for f in feats if f["properties"]["sggnm"] == n]) for n in names}
    seoul = unary_union(list(gu.values()))
    tests = {n: prep(g) for n, g in gu.items()}

    x0, y0, x1, y1 = seoul.bounds
    cells = {n: [] for n in names}
    for cx in range(int(np.floor(x0 / CELL_LON)), int(np.floor(x1 / CELL_LON)) + 1):
        for cy in range(int(np.floor(y0 / CELL_LAT)), int(np.floor(y1 / CELL_LAT)) + 1):
            sq = box(cx * CELL_LON, cy * CELL_LAT, (cx + 1) * CELL_LON, (cy + 1) * CELL_LAT)
            owner = next((n for n, t in tests.items() if t.contains(sq.centroid)), None)
            if owner:
                cells[owner].append(sq)

    # 한강 중심선 = 북쪽 구와 남쪽 구가 맞닿는 경계
    lines = [gu[a].boundary.intersection(gu[b].boundary) for a in NORTH for b in SOUTH if gu[a].touches(gu[b])]
    river_line = unary_union([l for l in lines if not l.is_empty])
    river_cells = [sq for sqs in cells.values() for sq in sqs if sq.intersects(river_line)]

    out = []
    for n in names:
        poly = unary_union(cells[n]).buffer(0)
        out.append({"type": "Feature", "properties": {"kind": "gu", "name": n, "cells": len(cells[n])}, "geometry": mapping(poly)})
    out.append({"type": "Feature", "properties": {"kind": "river", "name": "한강", "cells": len(river_cells)},
                "geometry": mapping(unary_union(river_cells).buffer(0))})
    CACHE.write_text(json.dumps({"type": "FeatureCollection", "source": raw.name, "cell_deg": [CELL_LON, CELL_LAT],
                                 "features": out}, ensure_ascii=False), encoding="utf-8")


CSS = f"""
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap">
<style>
  html, body {{ background: {CREAM}; }}
  .leaflet-container {{ background: {CREAM} !important; font-family: 'Malgun Gothic', '맑은 고딕', 'Noto Sans KR', sans-serif; }}
  .leaflet-overlay-pane svg path {{ shape-rendering: crispEdges; }}
  .gu-label {{ color: {WHITE}; font-weight: 700; font-size: 13px; white-space: nowrap; text-align: center;
    text-shadow: 1px 1px 0 #163F82, -1px 1px 0 #163F82, 1px -1px 0 #163F82, -1px -1px 0 #163F82; pointer-events: none; }}
  .leaflet-tooltip.px-tip {{ background: #FFFBEF; color: {INK}; border: 3px solid {INK}; border-radius: 0;
    box-shadow: 3px 3px 0 {INK}; font-size: 13px; padding: 4px 10px; }}
  .leaflet-tooltip.px-tip::before {{ display: none; }}
  .leaflet-bar {{ border: 3px solid {INK} !important; border-radius: 0 !important; box-shadow: 3px 3px 0 {INK}; }}
  .leaflet-bar a {{ border-radius: 0 !important; color: {INK}; background: #FFFBEF; font-family: 'Press Start 2P', monospace; font-size: 14px; }}
</style>
"""

TITLE = f"""
<div style="position:fixed;top:16px;left:64px;z-index:1000;padding:12px 16px;background:#FFFBEF;color:{INK};border:4px solid {INK};box-shadow:6px 6px 0 {INK}">
  <div style="font-family:'Press Start 2P',monospace;font-size:20px;color:#1F5FC4;text-shadow:3px 3px 0 #F4C430">SPOTFIT</div>
  <div style="font-size:14px;font-weight:700;margin-top:6px">서울 25개 자치구 도트 지도</div>
  <div style="font-size:12px;color:#5A5446">한 칸 = 약 400m · 한강은 북쪽·남쪽 구가 맞닿는 경계로 그림</div>
</div>
"""


def main():
    if not CACHE.exists():
        build()
    fc = json.loads(CACHE.read_text(encoding="utf-8"))
    gus = [f for f in fc["features"] if f["properties"]["kind"] == "gu"]
    river = next(f for f in fc["features"] if f["properties"]["kind"] == "river")

    m = folium.Map(location=[37.565, 126.985], zoom_start=12, min_zoom=10, max_zoom=13, tiles=None, control_scale=False,
                   zoom_snap=0.25)
    # 처음 화면이 서울 전체를 담도록 (위쪽 제목 상자 자리만큼 여백)
    x0, y0, x1, y1 = unary_union([shape(f["geometry"]) for f in gus]).bounds
    m.fit_bounds([[y0, x0], [y1, x1]], padding_top_left=(20, 130), padding_bottom_right=(20, 20))
    # 자치구: 파란 도트 + 구 사이 흰 선
    folium.GeoJson(
        {"type": "FeatureCollection", "features": gus}, name="자치구",
        style_function=lambda f: {"fillColor": BLUE, "fillOpacity": 1, "color": WHITE, "weight": 2.5},
        highlight_function=lambda f: {"fillColor": "#1F5FC4", "weight": 3.5},
        tooltip=folium.GeoJsonTooltip(fields=["name"], labels=False, class_name="px-tip"),
    ).add_to(m)
    # 한강: 연한 파란 도트
    folium.GeoJson(river, name="한강", interactive=False,
                   style_function=lambda f: {"fillColor": RIVER, "fillOpacity": 1, "color": RIVER, "weight": 0.5}).add_to(m)
    # 구 이름: 도트 다각형 안쪽의 한 점에 흰 글씨
    for f in gus:
        p = shape(f["geometry"]).representative_point()
        name = f["properties"]["name"]
        folium.Marker([p.y, p.x], icon=folium.DivIcon(html=f'<div class="gu-label">{name}</div>', icon_size=(70, 18),
                                                     icon_anchor=(35, 9), class_name="gu-label-wrap")).add_to(m)

    m.get_root().header.add_child(folium.Element(CSS))
    m.get_root().html.add_child(folium.Element(TITLE))
    m.save(OUT)
    print(f"[완료] {OUT.relative_to(REPO).as_posix()} · 자치구 {len(gus)}개, 한강 {river['properties']['cells']}칸")


if __name__ == "__main__":
    main()
