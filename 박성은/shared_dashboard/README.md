# SpotFit 공유 대시보드 · STEP 4 + STEP 5

**공개 공유 링크:** https://spotfit-park-2025.park24401859.chatgpt.site/#step5

로그인 없이 링크를 아는 누구나 열 수 있습니다. 기존 공유 주소를 유지하고 `05 유형 탐색 · STEP 5` 탭을 추가했습니다. Python 설치나 분석자의 PC 실행 상태와 무관하게 열립니다.

## 2026-11-14 추가한 화면

- 8유형의 전체 집계와 현재 업종·자치구·상권 유형 조건별 후보 수
- 세 축이 모두 일치하는 후보 탐색, 명시적 선택에 따른 부분 일치 포함
- 유형 수요 연결 가정(L→상주, V→유동) 켜기/끄기
- 상권별 세 축 원값·백분위·보류 사유, 기존 STEP 4 상세 화면 이동
- 임계값 민감도 및 축별 보류 사유, 분석 보고서·CSV 다운로드
- 모바일에서도 이용할 수 있는 정적 웹 화면

원본 STEP 4 분석은 `../step4_dashboard`, STEP 5 분석은 `../step5_personalization`에 있습니다. STEP 5 원본 기준 커밋은 `da58fc59b6fc4498c533c6890c24cee006aa8b72`입니다. 11월 12일 분석 보고서의 “공유 사이트는 수정하지 않았다”는 설명은 당시 상태이며, 이 폴더는 11월 14일에 추가한 웹 연결 작업입니다.

## 해석 범위

전체 76,591개 상권×업종 중 STEP 4 대상은 20,522개, 세 축 완전 후보는 9,267개, 보류는 11,255개입니다. 이 수는 고유 상권 수가 아닙니다.

L/V·E/P·S/D는 분석용 대리분류 가정이며 팀 최종 확정 전입니다. D는 네 분기 안의 변동성으로 성장·수요 증가를 뜻하지 않습니다. 실제 고객 성향, 사용자 금융 성향, 예산 적합성, 창업 성과를 추론하지 않습니다. 경계·결측을 보류로 유지합니다.

STEP 5 탐색은 Python 분석과 같은 공통 가중치(매출 30·경쟁 25·안정성 15·수요 30)를 씁니다. 유형별 가중치·보너스는 없습니다. 왼쪽 가중치와 고객층 설정은 STEP 4에 적용됩니다. 업종·자치구·상권 유형 필터는 두 화면에서 함께 사용합니다.

## 검증

- `validation.json`: 100개 업종, 76,591개 조합의 STEP 4 점수 일치, 20,522개 점수 대상 확인
- `validation-step5.json`: 전체 키·후보 수·보류 수·유형별 수 일치
- 기존 Python `explore()`와 160개 조건(1,280개 결과 행, 32개 빈 결과)의 후보 순서·점수·수요 연결·부분 일치 비교
- 브라우저에서 업종·지역·유형 선택, 부분 일치, 수요 연결, 보류 사유, 기존 상세 이동, CSV 내려받기, 후보 없는 업종, 모바일 화면 확인

## 재현

생성 데이터와 Plotly 자산은 원본 분석에서 내보냅니다. 중복된 대용량 파일은 이 폴더에 다시 올리지 않았습니다. 이 폴더에서 다음을 실행하세요(Node와 uv 필요).

```powershell
uv run --frozen --project ../step5_personalization python export_data.py
uv run --frozen --project ../step5_personalization python export_step5.py
node verify.js
node verify_step5.js
uv run --frozen --project ../step5_personalization python -m http.server 27185 --directory dist
```

미리보기: http://127.0.0.1:27185/#step5

`dist/`의 HTML·CSS·JavaScript가 공유 웹 화면 소스입니다. 내보내기 스크립트의 입력 경로만 팀 저장소 구조에 맞췄습니다. 운영 Site 소스·배포 식별자는 `publication.json`에서 확인할 수 있습니다. 인증 정보는 포함하지 않습니다.
