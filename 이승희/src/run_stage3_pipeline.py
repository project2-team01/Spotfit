# -*- coding: utf-8 -*-
"""
SpotFit 3단계 자동 실행기: 생성 → 보고서·대시보드 → 검증을 명령 하나로 실행한다.

실행 (저장소 루트에서):
    uv run python src/run_stage3_pipeline.py            # 전체 검증 (재실행 비교·변조 시험 포함, 오래 걸림)
    uv run python src/run_stage3_pipeline.py --quick    # 빠른 검증 (검사 1~7만)
    uv run python src/run_stage3_pipeline.py --check-only  # 생성 없이 현재 결과만 검증

동작 순서:
    1. 보호 파일(data/raw, 2단계 마트, PREPROCESSING.md)의 지문(sha256)을 기록한다.
    2. 프로젝트 폴더 밖의 임시 폴더에 src·data·report·images를 복사한다.
    3. 임시 폴더에서 build_stage3_features.py → build_stage3_report.py → verify_stage3.py를 실행한다.
    4. 세 단계가 모두 통과하면, 바뀐 3단계 결과물만 저장소로 옮긴다.
       하나라도 실패하면 저장소는 건드리지 않고, 임시 폴더를 남겨 원인을 볼 수 있게 한다.
    5. 끝나기 전에 보호 파일 지문이 그대로인지 다시 확인한다.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_DIR = Path(__file__).resolve().parents[1]

# 생성기가 바꿔도 되는 결과물 위치 (이 밖의 파일이 바뀌면 실패로 본다)
OUTPUT_DIRS = [
    Path("data") / "processed" / "stage3",
    Path("images") / "stage3",
]
OUTPUT_FILES = [
    Path("report") / "03_파생변수_설계보고서_2025Q4.md",
    Path("report") / "03_팀논의자료_2025Q4.md",
    Path("report") / "03_상권특성_대시보드_2025Q4.html",
]
# 절대 바뀌면 안 되는 보호 파일
PROTECTED_DIRS = [Path("data") / "raw", Path("data") / "processed" / "stage2"]
PROTECTED_FILES = [Path("data") / "PREPROCESSING.md"]
# 임시 폴더로 복사할 폴더
COPY_DIRS = ["src", "data", "report", "images"]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def tree_hashes(root, rel_dirs, rel_files=()):
    """root 아래 지정 폴더·파일의 {상대경로: sha256}."""
    out = {}
    for d in rel_dirs:
        base = root / d
        if base.exists():
            for p in sorted(base.rglob("*")):
                if p.is_file() and "__pycache__" not in p.parts:
                    out[p.relative_to(root).as_posix()] = sha256(p)
    for f in rel_files:
        p = root / f
        if p.exists():
            out[f.as_posix()] = sha256(p)
    return out


def all_hashes(root, rel_dirs):
    """src를 뺀 복사 대상 전체 지문. 생성기가 허용 밖 파일을 건드렸는지 확인하는 데 쓴다."""
    return tree_hashes(root, [Path(d) for d in rel_dirs])


def run_step(name, script, cwd, extra_args=(), log_lines=None):
    print(f"\n▶ {name} 실행 중... ({script})", flush=True)
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.Popen(
        [sys.executable, str(cwd / "src" / script), *extra_args],
        cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", env=env,
    )
    tail = []
    for line in proc.stdout:
        line = line.rstrip("\n")
        if log_lines is not None:
            log_lines.append(line)
        tail.append(line)
        tail = tail[-40:]
        # 검사 결과 줄만 화면에 보여 준다 (전체는 로그 파일에 저장)
        if any(k in line for k in ("[검사", "통과", "실패", "Error", "Traceback", "KILLED", "SURVIVED", "미차단", "완료")):
            print("   " + line, flush=True)
    code = proc.wait()
    sec = time.time() - t0
    if code == 0:
        print(f"✔ {name} 성공 ({sec:.0f}초)", flush=True)
    else:
        print(f"✘ {name} 실패 (종료코드 {code}, {sec:.0f}초). 마지막 출력:", flush=True)
        for line in tail:
            print("   | " + line)
    return code == 0


def main():
    ap = argparse.ArgumentParser(description="SpotFit 3단계 생성·검증 자동 실행기")
    ap.add_argument("--quick", action="store_true", help="검사 1~7만 실행 (재실행 비교·변조 시험 생략)")
    ap.add_argument("--check-only", action="store_true", help="생성하지 않고 현재 결과물만 검증")
    ap.add_argument("--keep-temp", action="store_true", help="성공해도 임시 폴더를 지우지 않음")
    args = ap.parse_args()

    started = time.strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 70)
    print("  [SpotFit 3단계] 자동 실행기: 생성 → 보고서·대시보드 → 검증")
    print(f"  시작 {started} | 검증 범위: {'빠른 검증(검사 1~7)' if args.quick else '전체 검증(검사 1~8 + 변조 시험)'}"
          f"{' | 생성 생략' if args.check_only else ''}")
    print("=" * 70)

    print("\n▶ 보호 파일 지문 기록 중 (data/raw, 2단계 마트, PREPROCESSING.md)...", flush=True)
    protected_before = tree_hashes(PROJECT_DIR, PROTECTED_DIRS, PROTECTED_FILES)
    print(f"✔ 보호 파일 {len(protected_before)}개 기록", flush=True)

    tmp = Path(tempfile.mkdtemp(prefix="spotfit_stage3_"))
    work = tmp / "PJT2-SpotFit"
    log_lines = []
    ok = False
    try:
        print(f"\n▶ 임시 작업 폴더로 복사 중... ({work})", flush=True)
        work.mkdir()
        for d in COPY_DIRS:
            shutil.copytree(PROJECT_DIR / d, work / d, ignore=IGNORE)
        for f in ("pyproject.toml", "uv.lock"):
            if (PROJECT_DIR / f).exists():
                shutil.copy2(PROJECT_DIR / f, work / f)
        before_run = all_hashes(work, [d for d in COPY_DIRS if d != "src"])
        print("✔ 복사 완료", flush=True)

        steps = []
        if not args.check_only:
            steps += [("1단계 특성표 생성", "build_stage3_features.py", ()),
                      ("2단계 보고서·대시보드 생성", "build_stage3_report.py", ())]
        steps.append(("3단계 검증", "verify_stage3.py", ("--mode=quick",) if args.quick else ()))

        for name, script, extra in steps:
            log_lines.append(f"\n===== {name} ({script}) =====")
            if not run_step(name, script, work, extra, log_lines):
                raise SystemExit(1)

        # 생성기가 허용된 결과물 밖의 파일을 건드리지 않았는지 확인
        after_run = all_hashes(work, [d for d in COPY_DIRS if d != "src"])
        allowed = {p.as_posix() for p in OUTPUT_FILES}
        allowed_dirs = [p.as_posix() + "/" for p in OUTPUT_DIRS]
        changed = sorted(k for k in set(before_run) | set(after_run) if before_run.get(k) != after_run.get(k))
        outside = [k for k in changed if k not in allowed and not any(k.startswith(d) for d in allowed_dirs)]
        if outside:
            print("\n✘ 생성기가 허용 범위 밖의 파일을 바꿨습니다. 저장소에 반영하지 않습니다:")
            for k in outside:
                print("   - " + k)
            raise SystemExit(1)

        # 저장소로 반영: 임시 폴더 결과물과 저장소 결과물을 비교해 다른 것만 복사
        new_out = tree_hashes(work, OUTPUT_DIRS, OUTPUT_FILES)
        cur_out = tree_hashes(PROJECT_DIR, OUTPUT_DIRS, OUTPUT_FILES)
        to_copy = sorted(k for k in new_out if cur_out.get(k) != new_out[k])
        stale = sorted(k for k in cur_out if k not in new_out)
        print("\n▶ 저장소 반영", flush=True)
        if args.check_only:
            print("   생성 생략 모드라 반영할 파일이 없습니다.")
        elif not to_copy:
            print(f"   결과물 {len(new_out)}개가 저장소와 완전히 같습니다. 바꿀 파일이 없습니다.")
        else:
            for k in to_copy:
                dst = PROJECT_DIR / k
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(work / k, dst)
                print(f"   갱신: {k}")
            print(f"   결과물 {len(new_out)}개 중 {len(to_copy)}개 갱신, {len(new_out) - len(to_copy)}개는 그대로")
        if stale:
            print("   참고: 생성기가 더는 만들지 않는 옛 파일이 저장소에 남아 있습니다 (지우지 않음):")
            for k in stale:
                print("   - " + k)

        ok = True
    finally:
        log_name = time.strftime("stage3_pipeline_%Y%m%d_%H%M%S.log")
        log_path = Path(tempfile.gettempdir()) / log_name
        log_path.write_text("\n".join(log_lines), encoding="utf-8")

        protected_after = tree_hashes(PROJECT_DIR, PROTECTED_DIRS, PROTECTED_FILES)
        if protected_after != protected_before:
            print("\n✘ 경고: 실행 중 저장소의 보호 파일이 바뀌었습니다!")
            ok = False
        else:
            print(f"\n✔ 보호 파일 {len(protected_after)}개 그대로 (data/raw, 2단계 마트, PREPROCESSING.md)")

        if ok and not args.keep_temp:
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            print(f"   임시 폴더를 남겨 두었습니다: {work}")

        print("=" * 70)
        if ok:
            print("  결과: 전부 통과했습니다.")
        else:
            print("  결과: 실패했습니다. 저장소의 결과물은 바꾸지 않았습니다.")
        print(f"  전체 실행 기록: {log_path}")
        print("=" * 70)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
