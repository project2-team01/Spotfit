"""희망 업종과 선호 유형으로 후보를 탐색한다. 창업 성과 예측이 아니다."""
import argparse
import json

import pandas as pd

from analyze_step5 import OUT, explore, normalize_type, save_csv


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--industry", required=True, help="서울 업종 코드 (예: CS100010)")
    p.add_argument("--type", required=True, help="LES/LED/LPS/LPD/VES/VED/VPS/VPD, 과거 G 코드도 변환 가능")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--allow-partial", action="store_true", help="미판정 축을 가진 부분 일치 후보도 별도 표기로 포함")
    args = p.parse_args()
    if args.limit < 1:
        p.error("limit은 1 이상이어야 합니다.")
    d = pd.read_parquet(OUT / "상권업종_유형후보_2025.parquet")
    try:
        result = explore(d, args.industry, args.type, args.limit, args.allow_partial)
    except ValueError as error:
        p.error(str(error))
    output = OUT / f"탐색_{args.industry}_{normalize_type(args.type)}_{'부분허용' if args.allow_partial else '정확일치'}.csv"
    save_csv(result, output)
    print(json.dumps({"rows": len(result), "output": output.name,
                      "message": "일치 후보 없음: 결과를 임의로 보충하지 않았습니다." if result.empty else "설계 가정에 따른 비교 후보이며 창업 추천 성능 검증 결과가 아닙니다."}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
