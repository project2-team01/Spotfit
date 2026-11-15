# 지도 디자인 시안 (folium 픽셀 아트)

대시보드 지도를 도트(픽셀 아트) 느낌으로 그린 디자인 시안입니다. 데이터는 STEP 4 **커피-음료** 종합 점수(2025년)입니다.

## 먼저 볼 파일 (채택안)

**[folium_pixel_gu_score_map_sample.html](folium_pixel_gu_score_map_sample.html)**: 브라우저로 열면 됩니다.
- 처음 화면은 25개 자치구를 구별 점수 중앙값 순위(5개 구씩 5단계)로 칠한 지도입니다. 구 이름표 숫자가 중앙값입니다.
- **구를 클릭하면** 그 구로 확대되고, 구 안에만 약 400m 점수 칸이 그려지며, 왼쪽에 상위 5곳(서울 순위 포함)이 나옵니다. "← 서울 전체"로 돌아갑니다.
- 서울 밖(경기·인천)은 이름 없는 도트 실루엣, 한강은 연한 파란 도트입니다.
- 두 화면의 색 기준이 다릅니다. 처음 화면은 구끼리의 순위, 상세 화면은 점수 자체(35·45·55·65점)입니다.

## 다른 시안

| 파일 | 내용 |
| :--- | :--- |
| `folium_pixel_map_sample.html` | 서울 전체를 약 400m 칸으로 칠한 점수 지도 (칸이 많아 빽빽함) |
| `folium_pixel_map_grid3x_sample.html` | 같은 지도를 약 1.2km 칸으로 키운 것 |
| `folium_pixel_gu_map_sample.html` | 점수 없이 자치구·한강만 그린 도트 지도 |

두 점수 칸 지도는 배경으로 Esri 회색 지도를 쓰므로 인터넷이 필요합니다. 나머지는 도트 글꼴만 인터넷에서 받습니다.

## 다시 만들기 (팀 저장소 루트에서)

folium·shapely는 STEP 4 환경에 없어서 실행할 때만 붙여 씁니다.

```bash
UV_PYTHON=3.12 uv run --project "이승희/step4_dashboard" --with folium --with shapely python "이승희/design_samples/folium_pixel_gu_score_map.py"   # 채택안
UV_PYTHON=3.12 uv run --project "이승희/step4_dashboard" --with folium --with shapely python "이승희/design_samples/folium_pixel_map.py"            # 400m 칸 (뒤에 3을 붙이면 1.2km 칸)
UV_PYTHON=3.12 uv run --project "이승희/step4_dashboard" --with folium --with shapely python "이승희/design_samples/folium_pixel_gu_map.py"         # 자치구 지도
```

- 경계 모양은 통계청 행정동 경계(2025-12-31, `HangJeongDong_ver20251231.geojson`)에서 만들어 아래 파일에 저장해 두었습니다. 이 파일들이 있으면 원본 없이 다시 그릴 수 있습니다.
  - `seoul_gu_pixel.geojson`: 25개 자치구 도트 모양과 한강 칸
  - `outside_pixel.geojson`: 서울 주변 시·군 도트 실루엣
  - `seoul_pixel_outline.geojson`: 서울 바깥 테두리
- 한강은 공개 지도 자료를 받지 못해, 한강 북쪽 구(마포·용산·성동·광진)와 남쪽 구가 맞닿는 경계선으로 그렸습니다. 서울 밖으로 이어지는 양 끝은 없습니다.

## 한계

- 시안이라 대시보드(marimo)에는 아직 넣지 않았습니다. 클릭 동작은 HTML 안의 스크립트라 marimo 안에서 동작하는지는 확인이 필요합니다.
- 구 단위 색은 구 하나를 중앙값 하나로 요약한 것이라 구 안의 차이는 클릭해서 봐야 합니다.
