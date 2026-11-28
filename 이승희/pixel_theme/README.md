# SpotFit 도트 디자인 (STEP 4·STEP 5 대시보드 공용)

STEP 4 상권 비교 점수 대시보드와 STEP 5 금융 MBTI 추천 대시보드가 함께 쓰는 디자인 파일입니다.

- 바탕은 노란빛 크림색(`#FBF3DC`)이고, 주요 색은 파랑(`#1F5FC4`) · 노랑(`#F4C430`) · 초록입니다.
- **큰 제목 `SPOTFIT`과 그림(핀·지도)만 도트**로 그립니다. 도트 글꼴은 Press Start 2P입니다.
- 본문은 맑은 고딕입니다. 맑은 고딕이 없는 컴퓨터에서는 Apple SD Gothic Neo나 Noto Sans KR로 보입니다.
- 차트 선·막대 색은 크림 바탕에서 대비 3:1 이상이 되도록 진하게 골랐습니다: 파랑 5.4, 진한 노랑 `#A67C00` 3.4, 초록 `#2E8B57` 3.8, 남색 `#163F82` 9.2. 이 색은 `../step4_dashboard/views.py`의 `LIGHT`에 있습니다.

## 파일

| 파일 | 내용 |
| :--- | :--- |
| `spotfit.css` | marimo 화면 바탕색·글꼴·도트 제목. 각 `app.py`의 `marimo.App(css_file=...)`로 불러옵니다 |
| `spotfit_head.html` | 탭·숫자 카드·안내 상자 모양. 이 위젯들은 marimo의 shadow DOM 안에 있어 CSS 파일이 닿지 않아서, 작은 스크립트로 같은 스타일을 위젯 안에 넣습니다. `marimo.App(html_head_file=...)`로 불러옵니다 |
| `header.py` | 대시보드 맨 위 도트 핀 로고와 `SPOTFIT` 제목 (folium 없이 가볍게 불러옴) |
| `pixel_map.py` | 자치구 픽셀 지도(folium). 구를 클릭하면 배경 지도 위에 그 구의 실제 상권 경계를 점수 색으로 그리고 상위 5곳을 보여 줍니다 |

- 지도 경계 모양은 `../design_samples/`의 `seoul_gu_pixel.geojson`(자치구·한강)과 `outside_pixel.geojson`(서울 밖 실루엣)을 읽습니다. 다시 만드는 방법은 [../design_samples/README.md](../design_samples/README.md)에 있습니다.

## 픽셀 지도 색 기준

- **대시보드·시안은 `upgrade=True`로 그립니다** (2026-11-18). 이때 서울 전체 화면 색은 구 중앙값과 서울 같은 업종 중앙값의 **차이**(±2·±5점 [가정])이고, 구 색 기준 버튼(종합·매출·경쟁·안정성·수요·상위 10% 상권 수), 표본 적은 구(10곳 미만 [가정]) 흐린 색·점선, 상권 상세 카드, 실제 구 경계(`../design_samples/seoul_gu_real.geojson`)가 켜집니다. 자세한 내용은 [../design_samples/README.md](../design_samples/README.md).
- **`upgrade=False`(예전 방식)의 서울 전체 화면:** 구 안 점수 상권의 종합 점수 중앙값을 구끼리 줄 세워 5단계로 나눕니다(구가 25개면 5개씩).
  - 구가 5개보다 적으면 양 끝과 사이 단계에 고르게 나누고, 구가 하나뿐이면 비교할 구가 없으니 가운데 단계로 칠합니다.
  - 조건에 맞는 점수 상권이 없는 구는 '점수 없음' 색입니다.
- **구 상세 화면:** 배경 지도(Esri 회색 지도와 지명, 인터넷 필요. CARTO는 iframe 안에서 'API KEY REQUIRED' 워터마크가 찍혀 쓰지 않음) 위에 그 구의 상권 경계를 종합 점수(0~100) 연속 색으로 칠합니다. 연한 파랑 `#D6E6FA` → `#5B8FE0` → 진한 파랑 `#163F82`로, STEP 4·5의 Plotly 지도와 같은 색입니다. 점수 없는 상권은 옅은 색입니다. 두 화면의 색 기준이 다릅니다(구 순위 vs 상권 점수).
- 서울 전체 화면의 빨간 핀 번호는 지금 조건의 상위 10곳, 구 상세 화면의 검은 번호는 그 구의 상위 5곳입니다. 상위 5곳 상자의 '서울 n위'는 서울 같은 업종(필터·유형 무관) 안의 순위입니다.

## 알아 둘 점

- **구 상세 화면 배경 지도:** 브이월드 API 키가 있으면 브이월드 회색 지도(19단계까지)를 씁니다. `이승희/.env.example`을 `이승희/.env`로 복사해 키를 넣고 `uv run --env-file 이승희/.env --project "이승희/step5_recommend" marimo run "이승희/step5_recommend/app.py"`로 엽니다. 키가 없으면 Esri 회색 지도 13단계 그림을 확대해 보여 줍니다(Esri는 한국에 14단계부터 'Map data not yet available'). 정적 HTML을 내보낼 때는 `--env-file`을 빼서 키가 파일에 들어가지 않게 합니다.
- 탭·숫자 카드 모양은 `marimo run`(앱 모드)과 HTML 내보내기에서만 바뀝니다. `marimo edit`(편집 모드)에서는 marimo가 보안상 `html_head_file`을 넣지 않아 기본 모양으로 보입니다.
- 어두운 화면에서는 크림 바탕 대신 marimo 기본 어두운 색을 쓰고, 글꼴과 도트 제목만 같습니다. 어두운 화면은 직접 확인하지 못했습니다.
- `spotfit_head.html`은 marimo 0.25.2의 위젯 구조(`role="tab"`, `bg-card`)에 맞춰 썼습니다. marimo 버전을 올리면 모양이 다시 기본으로 돌아갈 수 있습니다.
- 글꼴(Press Start 2P, Noto Sans KR)은 Google Fonts에서 받습니다. 인터넷이 없으면 도트 제목이 일반 글꼴로 보입니다.
