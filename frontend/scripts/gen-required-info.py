#!/usr/bin/env python3
"""data/ref/required_info.csv → src/lib/requiredInfo.ts (문의하기 화면이 제품군·문의 유형별 입력 항목을 만든다).
기준표가 바뀌면 이 스크립트를 다시 돌린다:  python3 frontend/scripts/gen-required-info.py
(챗봇 문의 전환은 서버가 만든 form.fields / missing_required 를 쓰므로 이 표는 '직접 문의하기' 진입용이다.)"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
rows = list(csv.DictReader(open(ROOT / "data/ref/required_info.csv", encoding="utf-8-sig")))
table: dict[str, dict[str, list[dict]]] = {}
for r in rows:
    blocking = set(r["blocking_fields"].split(";"))
    table.setdefault(r["family"], {})[r["category"]] = [
        {"key": k, "blocking": k in blocking} for k in r["required_fields"].split(";") if k
    ]
lines = []
for family, cats in table.items():
    lines.append(f"  {json.dumps(family)}: {{")
    for cat, fields in cats.items():
        lines.append(f"    {json.dumps(cat)}: {json.dumps(fields, ensure_ascii=False)},")
    lines.append("  },")
body = "{\n" + "\n".join(lines) + "\n}"
out = ROOT / "frontend/src/lib/requiredInfo.ts"
out.write_text(
    "// 자동 생성 파일 — frontend/scripts/gen-required-info.py (원본: data/ref/required_info.csv). 직접 고치지 않는다.\n"
    "export type RequiredField = { key: string; blocking: boolean };\n"
    "// 제품군 → 문의 유형(category_code) → 필수 항목(blocking = 없으면 처리가 시작되지 않는 항목)\n"
    f"export const REQUIRED_INFO: Record<string, Record<string, RequiredField[]>> = {body};\n",
    encoding="utf-8",
)
print("wrote", out.relative_to(ROOT), len(rows), "rows")
