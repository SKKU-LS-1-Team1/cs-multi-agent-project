"""슬라이드 예시 기반 분석 권장 자료. 접수·이관·SLA·우선순위를 바꾸지 않는다."""

import re
from collections.abc import Mapping

from cs_agent.rules.tables import RefTables, load_tables

_CATEGORIES = {"DEFECT", "INSTALL", "FW_UPDATE", "RETURN", "WARRANTY"}


def recommended_fields(family, category, text, error_code, tables: RefTables) -> list[str]:
    if str(category) not in _CATEGORIES or not family:
        return []
    fields = []
    for row in tables.investigation_info:
        if family not in row["family"].split(";"):
            continue
        codes = row["error_codes"].split(";") if row["error_codes"] else []
        if codes and error_code:
            matched = str(error_code).upper() in codes
        else:
            terms = [*row["keywords"].split(";"), *codes]
            matched = any(
                re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I)
                for term in terms
                if term
            )
        if matched:
            fields.extend(row["recommended_fields"].split(";"))
    return list(dict.fromkeys(fields))


def investigation_info(state: Mapping, tables: RefTables | None = None) -> dict | None:
    tables = tables or load_tables()
    inquiry, extraction = state.get("inquiry"), state.get("extraction")
    classification = state.get("classification")
    if not inquiry or not extraction or not classification:
        return None
    messages = state.get("customer_messages") or []
    text = messages[-1].get("body", inquiry.body) if messages else inquiry.body
    fields = recommended_fields(
        extraction.product_family,
        classification.category,
        inquiry.subject + "\n" + text,
        extraction.error_code,
        tables,
    )
    if not fields:
        return None
    values = dict(extraction.field_values)
    for key in ("serial_no", "error_code"):
        if value := getattr(extraction, key, None):
            values[key] = value
    provided = [f for f in fields if values.get(f) and f not in extraction.unconfirmed_fields]
    return {
        "recommended_fields": fields,
        "provided_fields": provided,
        "missing_fields": [f for f in fields if f not in provided],
        "note": (
            "제품·증상별 분석 권장 자료입니다. 없는 자료는 확인 필요로 남기고 이관할 수 있습니다."
        ),
    }
