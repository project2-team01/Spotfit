# STEP 2·3 산출물

- [STEP 2 전처리·결합 설계](../STEP2%28Codex%29.md)
- [STEP 3 파생변수 설계](../STEP3%28Codex%29.md)
- [실행 결과와 품질 점검](실행결과.md)
- [파생변수 사전](feature_dictionary.csv): 산출 52개, 보류 5개
- [테이블 스키마](table_schema.csv)
- [재현 코드](build_features.py)

프로젝트 루트 `seoul-commercial-analysis`에서 실행:

```bash
.venv/bin/python 김지영/step2_3/build_features.py
.venv/bin/python 김지영/step2_3/verify_outputs.py
```

`data/`에는 gzip 압축 CSV 6종, `qa/`에는 검증 및 검토 대상이 있다. 원본과 EDA 파일은 변경하지 않는다. CSV를 읽을 때 코드 컬럼은 문자열로 지정한다. 설계 문서·실행 요약은 자동 갱신되지 않는다. 저장 후 검증 결과는 `verify_outputs.py`로 갱신한다.
