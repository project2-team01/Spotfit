"""실제 생성한 검증 JSON에서 한국어 분석 보고서를 작성한다."""
import json
from pathlib import Path

import pandas as pd

import build_scores as bs
import views as v

HERE = Path(__file__).resolve().parent
REPORT = HERE / "report"


def main():
    bundle = v.load_bundle()
    counts = bundle.meta["counts"]
    core = json.loads((REPORT / "core_validation.json").read_text(encoding="utf-8"))
    exports = json.loads((REPORT / "export_validation.json").read_text(encoding="utf-8"))
    static = json.loads((REPORT / "static_check.json").read_text(encoding="utf-8"))
    performance = json.loads((REPORT / "performance.json").read_text(encoding="utf-8"))
    assert all(r["passed"] for r in core + exports) and static["passed"]
    original_score = bs.REPO / "이승희/step4_dashboard/data/상권_업종_비교점수_2025.parquet"
    assert bs.sha256(original_score) == bs.sha256(bs.OUT / "상권_업종_비교점수_2025.parquet"), "기존 팀 점수와 결과가 다름: 차이 분석 필요"
    baseline = v.filter_scope(bundle, "CS100010")
    top = set(baseline.loc[baseline.score_total.notna()].head(10).trdar_code)
    alternatives = [("기본", bs.DEFAULT_WEIGHTS, "avg"), ("경쟁 제외", dict(bs.DEFAULT_WEIGHTS, comp=0), "avg"),
                    ("유동 중심", bs.DEFAULT_WEIGHTS, "floating"), ("직장인 중심", bs.DEFAULT_WEIGHTS, "worker"),
                    ("주민 중심", bs.DEFAULT_WEIGHTS, "resident"),
                    ("안정성 40", dict(sales=20, comp=20, stab=40, dem=20), "avg")]
    sensitivity = []
    for name, weights, mode in alternatives:
        s = v.filter_scope(bundle, "CS100010", weights=weights, demand_mode=mode)
        selected = set(s.loc[s.score_total.notna()].head(10).trdar_code)
        sensitivity.append({"비교 설정": name, "기본 상위10 유지": len(top & selected), "기본 상위10 교체": len(top - selected),
                            "점수 중앙값": round(float(s.score_total.median()), 3)})
    pd.DataFrame(sensitivity).to_csv(HERE / "data/커피_가중치고객층_민감도.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    lines = ["# 박성은 · STEP 4 분석 및 대시보드 검증 보고서", "", "기준일: 2026-11-09. 2025년 자료만 분석했습니다.", "",
             "## 결과와 출처", "",
             "김지영 님의 공통 데이터와 이승희 님의 STEP 4 구현을 재사용하고, 분기 패널에서 공통 입력을 독립 검증한 뒤 점수표를 다시 생성했습니다. 기존 팀 점수표와 재생성한 Parquet의 SHA-256이 동일합니다. 강사 피드백을 반영한 시각화·캐싱과 검증 근거를 추가했습니다.", "",
             "| 항목 | 결과 |", "|---|---:|",
             f"| 관광특구 제외 상권×업종 | {counts['cells']:,} |",
             f"| 점수 대상 상권×업종 | {counts['target_cells']:,} |",
             f"| 매출 영역까지 계산 가능한 조합 | {counts['sales_scored_cells']:,} |",
             f"| 점수 생성 업종 | {counts['scored_industries']} / 100 |",
             f"| 매출 영역 생성 업종 | {counts['sales_scored_industries']} / 100 |", "",
             "### 제외 사유", "", "| 사유 | 조합 수 |", "|---|---:|"]
    lines += [f"| {k} | {n:,} |" for k, n in counts["status"].items() if k != "점수 대상"]
    lines += ["", "### 매출 점수가 없는 사유", "", "| 사유 | 조합 수 |", "|---|---:|"]
    lines += [f"| {k} | {n:,} |" for k, n in counts["sales_area_status"].items() if k != "점수 있음"]
    lines += ["", "## 입력 검토", "",
              "분기 패널 304,775행·연간 표 77,694행·맥락 표 6,600행·상권 1,650행을 확인했습니다. 관광특구는 6곳, 비교 대상 상권은 1,644곳입니다. 전체 76,591개 유효 연간 조합에서 4분기 평균 점포·직접 계산 폐업률·축소 추정의 최대 절대 차이는 모두 0입니다. 기존 공통 데이터의 분모를 검증한 뒤 재사용했습니다.", "",
              "직장인구·상주인구·집객시설의 2025년 중 값 변경 상권은 각각 0곳입니다. 원자료의 통계 기준 시점이 확인되었다는 뜻은 아닙니다.", "",
              "## 설계 가정과 민감도", "",
              "가중치 30/25/15/30, 수요 대비 점포 수로 경쟁을 나타내는 방식, 수요의 백분위 평균은 운영 가정입니다. 결과는 성공 확률이나 최적 입지를 의미하지 않습니다. 지역 필터로 백분위를 다시 계산하지 않습니다.", "",
              "전체 점수 대상의 경쟁·수요 Spearman 상관은 0.470, 직장·상주 밀도 백분위의 상관은 -0.551입니다. 낮은 상관이 독립성을 증명하지는 않습니다. 업종별 분석에서 **미용재료는 32곳, 경쟁·수요 상관 0.817**로 중복 반영 경고 기준을 넘었습니다. 기본 규칙은 유지하고 화면과 설계표에 경고를 추가했습니다. 대안은 경쟁 가중치 0 또는 직장/주민 중심 수요로 바꿔 민감도를 비교하는 것입니다. 대안의 통계적 우월성은 검증되지 않았습니다.", "",
              "커피-음료는 1,522곳 중 960곳이 점수 대상이고 884곳에서 매출 점수를 계산합니다. 아래는 가중치·고객층을 바꾸었을 때 기본 상위 10곳의 구성 변화이며 추천 성능 평가가 아닙니다.", "",
              "| 설정 | 기본 10곳 유지 | 교체 | 점수 중앙값 |", "|---|---:|---:|---:|"]
    lines += [f"| {r['비교 설정']} | {r['기본 상위10 유지']} | {r['기본 상위10 교체']} | {r['점수 중앙값']:.3f} |" for r in sensitivity]
    lines += ["", "## 강사 피드백 반영", "",
              "- 막대와 레이더를 함께 제공하고, 실제 업종 중앙값을 표시합니다. 결측을 0점 꼭짓점으로 연결하지 않습니다.",
              "- 최대 4개 상권을 공통 0~100 축의 작은 막대로 비교합니다.",
              "- 분기 지표를 quarter_mart.parquet에 미리 저장하고, 지도용 정적 자료도 저장합니다.",
              "- 데이터 로드는 한 번만 수행하고 최근 64개 조회 조합을 캐시합니다. 원본 갱신 후 재생성·앱 재시작이 필요합니다.",
              "- 지도는 선택한 종류만 만들며 동일 화면에서 두 지도를 동시에 직렬화하지 않습니다.", "",
              "[강사 답변 원문](https://innercircledata13.slack.com/archives/C0C00701HEE/p1794179921956489)", "",
              "## 검증 13개", "", "| 번호 | 검사 | 결과 | 숫자·근거 |", "|---:|---|---|---|"]
    records = {r["number"]: r for r in core}
    records[11] = dict(number=11, name="marimo check", passed=static["passed"], evidence="종료 코드 0. static_check.json")
    records[12] = dict(number=12, name="HTML 실제 셀 실행", passed=all(r["passed"] for r in exports), evidence=f"{len(exports)}개 시나리오 내보내기, 실제 셀 오류 0. ancestor-stopped 제외")
    for no in range(1, 14):
        r = records[no]
        lines.append(f"| {no} | {r['name']} | {'통과' if r['passed'] else '실패'} | {r['evidence'].replace('|', '/')} |")
    lines += ["", "추가 검사: 캐시와 직접 계산 동일, 캐시 반환값 변형 방지, 비연속 분기 증감률 결측, 레이더 결측 선 끊김. UI는 4개 탭의 전환과 막대·레이더·상권 비교 그래프 표시를 브라우저에서 확인했습니다. 지도에서 종로3가역을 클릭한 뒤 상세 제목이 종로3가역·커피-음료로 바뀌는 것도 확인했습니다. [실제 상세 화면](상세화면_검증.jpg)", "",
              "## 성능과 측정 범위", "",
              f"커피-음료 {performance['areas']:,}개 상권 기준. 데이터 최초 로드 {performance['cold_load_ms']:.1f}ms. 조회 중앙값은 직접 계산 {performance['uncached_query']['median_ms']:.2f}ms, 캐시 {performance['cached_query']['median_ms']:.2f}ms. 지도 생성·직렬화 중앙값은 Altair {performance['altair_build_serialize']['median_ms']:.1f}ms, Plotly {performance['plotly_build_serialize']['median_ms']:.1f}ms입니다.", "",
              "동일 PC에서 5회 측정한 Python 처리 시간입니다. 강사 질의에 나온 기존 2초와 측정 범위가 같다고 볼 수 없습니다. 브라우저의 실제 렌더링·지도 타일 네트워크·다중 사용자 응답 시간은 정량 측정하지 못했습니다. 독립적인 속도 목표 달성으로 주장하지 않습니다.", "",
              "## 미확정 사항과 한계", "",
              "- 기본 가중치·수요 지표·경쟁 지표의 팀 최종 승인과 현실 타당성 검증이 필요합니다.",
              "- MBTI 유형별 가중치는 연결하지 않았고, 유형표 확정 후 연결한다는 안내만 표시합니다.",
              "- 성장성·예산·순이익·창업 성공 확률은 계산하지 않습니다. 분기 증감은 참고용입니다.",
              "- 소표본 5개·비교 상권 30곳은 운영 기준입니다. 대표성이나 통계적 신뢰도를 보장하지 않습니다.",
              "- 정적 HTML은 Python 필터가 작동하지 않아 탭별 파일을 따로 제공합니다. CDN과 배경 지도에 인터넷이 필요할 수 있습니다.",
              "- 실제 지도 클릭→상세 선택의 모든 경우와 여러 기기의 터치 조작은 완전 검증하지 못했습니다. 함수의 선택 해석과 표·드롭다운 대체 경로를 제공합니다.",
              "- 입력 파일과 다른 팀원 폴더의 보존은 SHA-256과 git status로 확인했습니다.", "",
              "## 주요 파일", "",
              "| 파일 | 역할 |", "|---|---|",
              "| build_scores.py / audit_inputs.py | 입력 검토·점수표·사전 계산 데이터 생성 |",
              "| views.py / app.py | 캐시·조회·차트 / marimo 화면 |",
              "| test_step4.py / verify_exports.py | 규칙·재현·변조 검사 / 정적 검사·실제 화면 내보내기 |",
              "| benchmark.py | Python 처리·직렬화 측정 |",
              "| data/ | 점수표·설계표·업종별 상태·상관·민감도·분기 mart·지도 |",
              "| report/ | 탭별 HTML과 검증 JSON·본 보고서 |", "",
              "실행 명령과 정적 HTML 링크는 [README](../README.md)에 있습니다."]
    (REPORT / "분석_검증_보고서.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("분석 보고서와 커피 업종 민감도 표 생성 완료")


if __name__ == "__main__":
    main()
