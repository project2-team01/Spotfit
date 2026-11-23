# SpotFit 팀 자료 재검토 통합본 · 2026-11-23

[공유 대시보드](https://spotfit-park-2025.park24401859.chatgpt.site/#s1) · [판단 근거와 변경 내용](REVIEW.md) · [더블클릭 실행 HTML](report/SpotFit_팀통합_최종대시보드.html)

팀원의 최신 분석·화면을 목적 적합성·재현성·해석 가능성으로 비교했다. 김지영의 10개 보고서 화면과 STEP 6 시각화, 이승희의 공식 지표·최신 검사지·픽셀 지도 자산, 박성은의 독립 검증·공유 배포를 결합했다. 원본 팀원 폴더와 이전 결과는 수정하지 않았다.

기본 점수는 공통 원패널 재계산 및 지영·최신 승희 저장 결과와 대상 20,522개에서 일치한다. 예전 성은 점수는 126개가 다르다. 유형은 희망 업종 E/P와 공식 S/D로 통일했다. 가중치·경계값은 성과로 검증된 최적값이 아니라 운영 가정이다.

```powershell
# 팀 저장소 루트, 기존 고정 환경 사용
uv run --frozen --project "박성은/step5_personalization" python "박성은/team_unified_final/build.py"
cd "박성은/team_unified_final"
node verify.js
```

`web/`은 추적하는 최종 화면 원본이다. 상위 팀원 화면과의 연결을 다시 생성하려면 `adapt_sources.py`를 먼저 실행한다. 화면만 바뀌고 입력 데이터가 그대로라면 `build.py --assemble-only`로 재조립할 수 있다. 전체 재계산은 `build.py`다.

- `data/audit.json`: 공통 원입력 재계산, 팀원 점수·유형 대조, 분모·SHA-256
- `data/통합_분석.parquet`: 조합별 원값·점수·유형·보류 사유
- `data/LV_정의차이.csv`, `data/EP_정의차이.csv`: 분류 정의가 다른 조합
- `report/validation.json`: 독립 Python과 브라우저 계산 함수 대조
- `report/browser_check.json`: 실제 브라우저 확인 결과
- `publication.json`: 공유 배포 버전

생성 중간 파일 `data/payload.json`, `data/oracle.json`, `dist/index.html`은 Git에 중복 저장하지 않는다. 완성 HTML은 `report/`에 포함한다. 검증은 구현·재현 검증이며 창업 성공·심리검사 타당도 검증이 아니다.
