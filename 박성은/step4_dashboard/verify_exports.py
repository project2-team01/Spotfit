"""실제 marimo 전체 탭·경계 상황을 실행해 HTML과 검증 증거를 저장한다."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["MARIMO_SKIP_UPDATE_CHECK"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"


def main():
    import views as v
    (HERE / "report").mkdir(exist_ok=True)
    check = subprocess.run([sys.executable, "-m", "marimo", "check", str(HERE / "app.py")],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
    (HERE / "report/static_check.json").write_text(json.dumps({
        "passed": check.returncode == 0, "returncode": check.returncode,
        "stdout": check.stdout, "stderr": check.stderr}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert check.returncode == 0, check.stderr
    bundle = v.load_bundle()
    unsupported = bundle.industries.loc[~bundle.industries["매출_제공_업종"] & bundle.industries["점수_생성"], "업종_코드"].iloc[0]
    noscore = bundle.industries.loc[~bundle.industries["점수_생성"], "업종_코드"].iloc[0]
    empty_args = None
    for code in bundle.industries.loc[bundle.industries["점수_생성"], "업종_코드"]:
        scope = v.filter_scope(bundle, code)
        for gu in sorted(bundle.scores.gu_name.unique()):
            if scope.loc[scope.gu_name.eq(gu) & scope.trdar_type.eq("전통시장")].empty:
                empty_args = ["--industry", code, "--gu", gu, "--type", "전통시장"]
                break
        if empty_args:
            break
    cases = [("04_상권비교점수_대시보드_2025", []), ("tab2_detail", ["--tab", "1"]),
             ("tab3_distribution", ["--tab", "2"]), ("tab4_limits", ["--tab", "3"]),
             ("map_plotly", ["--map", "plotly"]), ("case_no_sales", ["--industry", unsupported]),
             ("case_no_score", ["--industry", noscore]), ("case_empty", empty_args),
             ("case_zero_weights", ["--zero", "true"])]
    if bundle.meta.get("high_overlap_industries"):
        cases.append(("case_high_overlap", ["--industry", bundle.meta["high_overlap_industries"][0]["업종_코드"]]))
    results = []
    for name, args in cases:
        output = HERE / "report" / f"{name}.html"
        start = time.perf_counter()
        command = [sys.executable, "-m", "marimo", "export", "html", str(HERE / "app.py"),
                   "--no-include-code", "-o", str(output), "-f", "--", *args]
        run = subprocess.run(command, cwd=HERE, capture_output=True, text=True, encoding="utf-8", timeout=180)
        text = output.read_text(encoding="utf-8") if output.exists() else ""
        text = re.sub(r"(?m)^[ \t]+$", "", text)
        if output.exists():
            output.write_text(text, encoding="utf-8", newline="\n")
        # HTML에 실제로 저장된 셀 출력 전체를 검사한다.
        marker = re.search(r'"session"\s*:\s*', text)
        session = json.JSONDecoder().raw_decode(text[marker.end():])[0] if marker else None
        assert session is not None, "HTML session 정보 없음"
        errors = [out for cell in session["cells"] for out in cell["outputs"]
                  if out.get("type") == "error" and out.get("ename") != "ancestor-stopped"]
        errors += re.findall(r"MarimoExceptionRaisedError|Traceback \(most recent call last\)", run.stderr)
        result = {"case": name, "args": args, "passed": run.returncode == 0 and not errors and len(text) > 10000,
                  "returncode": run.returncode, "error_markers": errors, "bytes": output.stat().st_size if output.exists() else 0,
                  "seconds": round(time.perf_counter() - start, 3), "stderr": run.stderr[-5000:]}
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    (HERE / "report/export_validation.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not all(r["passed"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
